# Wrapper around senspot and senspot-file

# It is by no means complete, but serves as a starting point.
# Look at the main at the bottom of the file to see an example of it in action.

# Current TODOs:
# Implement payload_size in senspot
# A "bytes" datatype in senspot
# Support WooF forwarding
# Retrieve sequence number from senspot-put


import base64
from dataclasses import dataclass, field
import datetime
import io
import math
import os
from pathlib import Path
import shutil
from subprocess import Popen, PIPE
import re
import random
from typing import Optional, cast
import stat


def parse_senspot_get(msg):
    pattern = re.compile(
        r"^(?P<data>.*?)\s+time:\s+(?P<time>\S+)\s+"
        r"(?P<ip_source>\S+)\s+seq_no:\s+(?P<seq_no>\d+)$"
    )
    match = pattern.match(msg)
    if not match:
        raise ValueError(f"Invalid message format: {msg!r}")

    result = match.groupdict()
    result["seq_no"] = int(result["seq_no"])
    result["time"] = datetime.datetime.fromtimestamp(float(result["time"]))
    return result


def update_cspot(bin_path="."):
    cmd = f"{bin_path}/update-cspot-distribution.sh"
    proc = Popen([cmd], stdout=PIPE, stderr=PIPE)

    result, err = proc.communicate()
    if proc.returncode != 0:
        raise OSError(f"Error calling {cmd}: {result, err}")

    return result


@dataclass
class WooFItem:
    seq_no: int
    data: bytes | float | str | int
    ip_source: str
    timestamp: datetime.datetime


@dataclass
class FileWooFLocations:
    size: int = -1
    dedup_seq_no: int = -1
    flags: int = 0
    seq_no: int = -1
    block_no: int = 0


@dataclass
class FileWooFItem:
    version_no: int = -1  #
    path: Optional[str] = None  #
    is_emulated: bool = False  #
    size: int = 0  #
    timestamp: datetime.datetime = datetime.datetime.fromtimestamp(0)  #
    blocks: int = 0  #
    last_block_size: int = 0  #
    element_size: int = 0  #
    locations: list[FileWooFLocations] = field(default_factory=list)
    transfer_time: float = 0.0  #
    start_seq_no: int = -1  #
    end_seq_no: int = -1  #


class FileWooF:
    # for senspot-file. Has get and put for WooF-like access
    def __init__(self, name, bin_path="."):
        self.name = name
        self.bin = bin_path
        if self.bin[-1] == "/":
            self.bin = self.bin[0:-1]

    def fileInit(self, element_size: int = 32768, history_size: int = 32):
        if self.name[0:7] == "woof://":
            raise ValueError("fileInit only applicable on direct woof file paths")

        el_kb = math.ceil(element_size / 1024)
        cmd = f"{self.bin}/senspot-file-init"

        proc = Popen(
            [cmd, "-W", self.name, "-M", str(el_kb), "-s", str(history_size)],
            stdout=PIPE,
            stderr=PIPE,
            pass_fds=(),
        )
        result, err = proc.communicate()
        if proc.returncode != 0:
            raise OSError(f"Error calling {cmd}: {result!r} {err!r}")

        return result.decode("latin-1")

    def get(self, version_no=-1, start_seq_no=-1, scan_start_seq_no=-1) -> WooFItem:
        # same as WooFGet but for bigger items. Emulates WooF but for any size elements
        fd = os.memfd_create(f"sf_vwoof_{random.randint(0,1000000)}")
        path = f"/proc/self/fd/{fd}"
        item = self.recv(path, version_no, start_seq_no, scan_start_seq_no, pass_fd=fd)
        os.lseek(fd, 0, os.SEEK_SET)
        chunks = []
        chunk = os.read(fd, 1024 * 256)
        while chunk:
            chunks.append(chunk)
            chunk = os.read(fd, 1024 * 256)
        os.close(fd)
        data = b"".join(chunks)

        return WooFItem(
            seq_no=item.version_no,
            data=data,
            ip_source="0.0.0.0",
            timestamp=item.timestamp,
        )

    def put(self, data: bytes):
        # same as WooFPut but for bigger items. Emulates WooF but for any size elements

        fd = os.memfd_create(f"sf_vwoof_{random.randint(0,1000000)}")
        os.write(fd, data)
        os.lseek(fd, 0, os.SEEK_SET)
        path = f"/proc/self/fd/{fd}"
        out = self.send(path, pass_fd=fd)
        os.close(fd)

        out.path = "<vwoof>"
        out.is_emulated = True
        return out.version_no, out.end_seq_no

    # Seqno | file blocks   | version
    # 37
    # 36      block 0       | Version 13 "start_seq"     <---- scan start (goes down)
    # 35      block 1       |                                        |
    # 34      block 2       | "end_seq"                              V
    # 33      block 0       | Version 12
    # ...
    # 0

    def recv(
        self,
        write_to: str,
        version_no=-1,
        end_seq_no=-1,
        scan_start_seq_no=-1,
        pass_fd=None,
    ):

        if scan_start_seq_no < end_seq_no:
            raise ValueError(
                "Scan is set to start prior to the start seq, meaning the file will always be skipped"
            )

        cmd = f"{self.bin}/senspot-file-recv"

        full_cmd = [cmd, "-W", self.name, "-f", write_to, "-V"]
        if version_no >= 0:
            full_cmd.append("-v")
            full_cmd.append(str(version_no))
        if end_seq_no >= 0:
            full_cmd.append("-m")
            full_cmd.append(str(end_seq_no))

        if scan_start_seq_no >= 0:
            full_cmd.append("-s")
            full_cmd.append(str(scan_start_seq_no))

        fds = tuple()  # type: ignore
        if pass_fd is not None:
            fds = (pass_fd,)
        proc = Popen(full_cmd, stdout=PIPE, stderr=PIPE, pass_fds=fds)

        result_b, err = proc.communicate()
        result = result_b.decode("latin-1")
        if proc.returncode != 0:
            raise OSError(f"Error calling {cmd}: {result_b!r} {err!r}")

        # parse -V output
        out = FileWooFItem(path=write_to)
        for line in result.split("\n"):
            line = line.strip()
            colon_tokens = line.split(":")
            if len(colon_tokens) == 2:
                match colon_tokens[0]:
                    case "version":
                        out.version_no = int(colon_tokens[1].strip())
                        continue
                    case "creation_time":
                        start_paran = colon_tokens[1].find("(") + 1
                        tmstp = int(colon_tokens[1][start_paran:-1])
                        out.timestamp = datetime.datetime.fromtimestamp(tmstp)
                        continue
                    case "start":
                        out.start_seq_no = int(colon_tokens[1].strip())
                        continue
                    case "end":
                        out.end_seq_no = int(colon_tokens[1].strip())
                        continue
                    case _:
                        pass
            # get last line (time and start):
            ln = re.search(r"\(([\d.]+)\s+bytes\s+in\s+([\d.]+)\s+sec\)", line)
            if ln:
                out.size = int(float(ln.group(1)))
                out.transfer_time = float(ln.group(2))
                continue

            # get location records:
            ln = re.search(r"wrote\s+(\d+)\s+from\s+(\d+)\s+dedup:\s+(\d+)", line)
            if not (ln):
                continue  # unknown!

            # remainder is location records
            loc = FileWooFLocations(
                size=int(float(ln.group(1))),
                seq_no=int(ln.group(2)),
                dedup_seq_no=int(ln.group(3)),
                block_no=len(out.locations),
            )
            out.locations.append(loc)
        out.blocks = len(out.locations)
        out.last_block_size = out.locations[-1].size
        return out

    def send(self, file_path, pass_fd=None):
        cmd = f"{self.bin}/senspot-file-send"

        full_cmd = [cmd, "-W", self.name, "-f", file_path, "-V"]

        fds = tuple()  # type: ignore
        if pass_fd is not None:
            fds = (pass_fd,)
        proc = Popen(full_cmd, stdout=PIPE, stderr=PIPE, pass_fds=fds)

        result_b, err = proc.communicate()
        result = result_b.decode("latin-1")
        if proc.returncode != 0:
            raise OSError(f"Error calling {cmd}: {result_b!r} {err!r}")

        # parse -V output
        out = FileWooFItem(path=file_path)
        for line in result.split("\n"):
            line = line.strip()
            colon_tokens = line.split(":")
            if len(colon_tokens) == 2:
                match colon_tokens[0]:
                    case "version":
                        out.version_no = int(colon_tokens[1].strip())
                        continue
                    case "creation_time":
                        start_paran = colon_tokens[1].find("(") + 1
                        tmstp = int(colon_tokens[1][start_paran:-1])
                        out.timestamp = datetime.datetime.fromtimestamp(tmstp)
                        continue
                    case "size":
                        out.size = int(colon_tokens[1].strip())
                        continue
                    case "blocks":
                        out.blocks = int(colon_tokens[1].strip())
                        continue
                    case "last":
                        out.last_block_size = int(colon_tokens[1].strip())
                        continue
                    case "el_size":
                        out.element_size = int(colon_tokens[1].strip())
                        continue
                    case _:
                        pass
            # now are other fields
            if line[0:3] == "EOF":
                out.end_seq_no = int(line[len("EOF put at ") :])
                continue

            # get last line (time and start):
            ln = re.search(
                r"\((?:[\d.]+)\s+bytes\s+in\s+([\d.]+)\s+sec\)\s+start_seqno:\s+(\d+)",
                line,
            )
            if ln:
                out.transfer_time = float(ln.group(1))
                out.start_seq_no = int(ln.group(2))
                continue

            # get location records:
            ln = re.search(
                r"putting\s+block\s+(\d+),\s+size\s+(\d+),\s+dedup_seqno\s+(\d+)\s+flags:\s+(\d+)\s+\w+\s+seqno:\s+(\d+)",
                line,
            )
            if not (ln):
                continue  # unknown!

            # remainder is location records
            loc = FileWooFLocations(
                block_no=int(ln.group(1)),
                size=int(ln.group(2)),
                dedup_seq_no=int(ln.group(3)),
                flags=int(ln.group(4)),
                seq_no=int(ln.group(5)),
            )
            out.locations.insert(0, loc)
        return out

    def getLatestSeqno(self):
        cmd = f"{self.bin}/senspot-file-recv"

        full_cmd = [cmd, "-W", self.name, "-l"]

        proc = Popen(full_cmd, stdout=PIPE, stderr=PIPE)

        result_b, err = proc.communicate()
        result = result_b.decode("latin-1")
        if proc.returncode != 0:
            raise OSError(f"Error calling {cmd}: {result_b!r} {err!r}")

        items = re.search(
            r"version\s+(\d+):(\d+)\s+at\s+\d+,\s+created:\s+.+?\((\d+)\)\s+size:\s+(\d+)\s+start_seqno:\s+(\d+)",
            result,
        )
        if not (items):
            raise OSError(f"Malformed output from {cmd}: {result}")

        return FileWooFItem(
            version_no=int(items.group(1)),
            end_seq_no=int(items.group(2)),
            timestamp=datetime.datetime.fromtimestamp(int(items.group(3))),
            size=int(items.group(4)),
            start_seq_no=int(items.group(5)),
        )

    def getAllSeqno(self):
        # generator
        cmd = f"{self.bin}/senspot-file-recv"

        full_cmd = [cmd, "-W", self.name, "-L"]

        proc = Popen(full_cmd, stdout=PIPE, stderr=PIPE, text=True, bufsize=1)
        try:
            for line in proc.stdout:
                items = re.search(
                    r"version\s+(\d+):(\d+)\s+at\s+\d+,\s+created:\s+.+?\((\d+)\)\s+size:\s+(\d+)\s+start_seqno:\s+(\d+)",
                    line,
                )
                if not (items):
                    raise OSError(f"Malformed output from {cmd}: {line}")
                yield FileWooFItem(
                    version_no=int(items.group(1)),
                    end_seq_no=int(items.group(2)),
                    timestamp=datetime.datetime.fromtimestamp(int(items.group(3))),
                    size=int(items.group(4)),
                    start_seq_no=int(items.group(5)),
                )
        finally:
            proc.stdout.close()
            proc.stderr.close()
            proc.wait()


class WooF:
    def __init__(self, name, bin_path=None, is_jumbo=False):
        self.name = name

        if bin_path is None:
            found = shutil.which("senspot-get")
            if found is None:
                raise OSError("senspot is not installed!")
            self.bin = str(Path(found).parent)
        else:
            self.bin = cast(str, bin_path)
        if self.bin[-1] == "/":
            self.bin = self.bin[0:-1]

        self.jumbo = is_jumbo

    def WooFCreate(self, element_size, history_size):
        if self.name[0:7] == "woof://":
            raise ValueError("WooFCreate only applicable on direct woof file paths")

        # Run `senspot_get -W woof://path/to/woof`
        cmd = f"{self.bin}/senspot-init"

        # TODO: senspot does not support custom element sizes, though WooF does.

        proc = Popen(
            [cmd, "-W", self.name, "-s", str(history_size)], stdout=PIPE, stderr=PIPE
        )

        result, err = proc.communicate()
        if proc.returncode != 0:
            raise OSError(f"Error calling {cmd}: {result!r} {err!r}")

        return result.decode("latin-1")

    def WooFReset(self):
        if self.name[0:7] == "woof://":
            raise ValueError("WooFReset only applicable on direct woof file paths")

        # Run `senspot_get -W woof://path/to/woof`
        cmd = f"{self.bin}/senspot-init"

        proc = Popen([cmd, "-W", self.name, "-R"], stdout=PIPE, stderr=PIPE)

        result, err = proc.communicate()
        if proc.returncode != 0:
            raise OSError(f"Error calling {cmd}: {result!r} {err!r}")

        return result.decode("latin-1")

    def WooFPut(
        self,
        element: bytes | float | str | int,
        handler_name: Optional[str] = None,
        forward=False,
    ):
        cmd = f"{self.bin}/senspot-put"
        if self.jumbo:
            cmd = f"{self.bin}/senspot-put-jumbo"

        # serialize data / pass into pipe
        if isinstance(element, float):
            data = (str(element) + "\n").encode("latin-1")
            dflag = "D"
        elif isinstance(element, str):
            data = element.encode("latin-1")
            dflag = "S"

            # TODO: right now, senspot doesn't accept strings with spaces /

        elif isinstance(element, int):
            data = (str(element) + "\n").encode("latin-1")
            dflag = "I" if abs(element) < 2**31 else "L"
        else:
            # Do b64 encoding for now
            dflag = "S"
            data = base64.b85encode(element)  # 5/4 inefficency ... stores 819 bytes max

        # TODO: Support WooF forwarding....

        if len(data) > 1024 and not (self.jumbo):
            raise ValueError("Data input too big!")
        elif len(data) > 8 * 1024:
            raise ValueError("Data input too big! JUMBO YES")

        if handler_name is not None:
            proc = Popen(
                [cmd, "-W", self.name, "-H", handler_name, "-T", dflag], stdin=PIPE
            )
        else:
            proc = Popen([cmd, "-W", self.name, "-T", dflag], stdin=PIPE)

        result, err = proc.communicate(data)
        if proc.returncode != 0:
            raise OSError(f"Error calling {cmd}: {result!r} {err!r}")

        #  TODO: retrieve sequence number - currently senspot does not implement this.
        # easy patch to senspot-put. See line 117 on cspot_interface.

        # TODO: Return seq no
        return -1

    def WooFGet(self, type, seq_no=-1) -> WooFItem | None:
        return self.WooFGets(type, seq_no, items=1)[0]

    def WooFGets(self, type, seq_no=-1, items=1) -> list[WooFItem | None]:
        # Run `senspot_get -W woof://path/to/woof`
        cmd = f"{self.bin}/senspot-get"
        if self.jumbo:
            cmd = f"{self.bin}/senspot-get-jumbo"

        if seq_no == -1:
            proc = Popen(
                [cmd, "-W", self.name, "-C", str(items)], stdout=PIPE, stderr=PIPE
            )
        else:
            sn = str(seq_no)
            proc = Popen(
                [cmd, "-W", self.name, "-S", sn, "-C", str(items)],
                stdout=PIPE,
                stderr=PIPE,
            )
        result_b, err = proc.communicate()
        result = result_b.decode("latin-1")
        if proc.returncode != 0:
            raise OSError(f"Error calling {cmd}: {result} {err!r}")
        # parse result.
        # '{data} time: {time} {ip_source} seq_no: {seq_no}' Data may contain spaces.
        out: list[WooFItem | None] = []
        for item in result.split("\n"):
            if item.strip() == "":
                continue
            try:
                output = parse_senspot_get(item)
            except ValueError:
                continue
            try:
                # check type
                if type is float:
                    data = float(output["data"])
                elif type is str:
                    data = output["data"]
                elif type is int:
                    data = int(output["data"])
                elif type is bytes:
                    data = base64.b85decode(output["data"])  # type: ignore
                else:
                    data = output["data"]
            except ValueError:
                raise ValueError(
                    f"Likely not correct type! Received raw: {output['data']}"
                )

            out.append(
                WooFItem(
                    data=data,
                    seq_no=output["seq_no"],
                    ip_source=output["ip_source"],
                    timestamp=output["time"],
                )
            )
        if len(out) == 0:
            return [None]

        return out

    def WooFGetEarliestSeqno(self):
        # Run `senspot_get -W woof://path/to/woof`
        cmd = f"{self.bin}/senspot-get"
        if self.jumbo:
            cmd = f"{self.bin}/senspot-get-jumbo"

        proc = Popen([cmd, "-W", self.name, "-e"], stdout=PIPE, stderr=PIPE)

        result, err = proc.communicate()
        if proc.returncode != 0:
            raise OSError(f"Error calling {cmd}: {result!r} {err}")

        return int(result)


if __name__ == "__main__":
    # some tests
    YOUR_WOOF_HERE = ""
    YOUR_SENSPOT_FILE_WOOF = ""

    with open("/tmp/a_file.txt", "w") as f:
        f.write("Hello World form a file")

    uri = YOUR_WOOF_HERE
    test_woof = WooF(uri, bin_path="bin/")
    test_woof.WooFPut("Hello World!")
    item = test_woof.WooFGet(str)
    assert item is not None
    print(item.data)
    print("===")

    test_woof.WooFPut(1234)
    item = test_woof.WooFGet(int)
    assert item is not None
    print(item.data)
    print("===")

    test_woof.WooFPut(5.27)
    item = test_woof.WooFGet(float)
    assert item is not None
    print(item.data)
    print("===")

    test_woof.WooFPut(b"\xac\xe0")
    item = test_woof.WooFGet(bytes)
    assert item is not None
    print(item.data)
    print("===")

    # Do list of items.
    for i in range(10):
        test_woof.WooFPut(i)
        print("Put complete ===")

    # get latest seq
    latest = test_woof.WooFGet(int)
    assert latest is not None
    items = test_woof.WooFGets(int, latest.seq_no - 9, 10)

    for item in items:
        assert item is not None
        print(item.data)

    # Test senspot-file
    print("===== Senspot File Test ======")
    woof = YOUR_SENSPOT_FILE_WOOF
    fwoof = FileWooF(woof, bin_path="bin/")

    v_no, _ = fwoof.put(b"Hello World!")
    item = fwoof.get(v_no)
    print(item.data)
    print("===")

    # Test actual file
    fwoof = FileWooF(woof, bin_path="bin/")

    record = fwoof.send("/tmp/a_file.txt")

    item_meta = fwoof.recv("/tmp/b_file.txt", record.version_no)
    print(f"Wrote to {item_meta.path} {item_meta.size} bytes")
    print("===")

    # Test utilities
    item_meta = fwoof.getLatestSeqno()
    print(f"Latest version is: {item_meta.version_no}:{item_meta.end_seq_no}")

    # Get all versions
    for item_meta in fwoof.getAllSeqno():
        print(f"Have version: {item_meta.version_no}:{item_meta.end_seq_no}")
