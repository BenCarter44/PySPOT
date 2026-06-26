// senspot.hpp
// Wrapper around the senspot command-line utility.

#ifndef PYSPOT_CPP_INCLUDE_SENSPOT_HPP
#define PYSPOT_CPP_INCLUDE_SENSPOT_HPP

#include "boost_process_compat.hpp"
#include <iostream>
#include <string>

#include "str.hpp"

// TODO: figure out where to use boost::process::child and where to use
// boost::process::system.
class senspot
{
  public:
    // RAII idiom: the CSPOT namespace is automatically created when this object
    // is initialized and the namespace is cleaned up when this object is
    // destroyed.
    senspot(const std::string &_senspot_dir) : senspot_dir(_senspot_dir)
    {

        // First, we need to check if there is already a CSPOT namespace
        // running. If there is, we do not need to start one.
        int pgrep_exitcode = bp::system("/usr/bin/pgrep", "woofc");
        if (pgrep_exitcode == 0)
        {
            return;
        }

        std::cout << "Expected senspot binaries to be located at " << senspot_dir << std::endl;
        bp::child c(senspot_dir + "/woofc-namespace-platform", bp::std_out > "namespace.log",
                    bp::std_err > "namespace.log");

        c.detach();
    }

    // TODO: not sure if this is sufficient to cleanly terminate everything.
    // We explicitly don't assert that the exit code is 0 because the namespace
    // might already have been cleaned up.
    ~senspot()
    {
        int exitcode1 = bp::system("/usr/bin/pkill", "-9", "woofc-namespace");
        int exitcode2 = bp::system("/usr/bin/pkill", "-9", "woofc-container");
    }

    // Create a WOOF with a given name and size
    void senspot_init(const std::string &woof_name, int woof_sz)
    {
        std::string cmd = senspot_dir + "/senspot-init";
        std::vector<std::string> args = {"-W", woof_name, "-s", std::to_string(woof_sz)};
        bp::child c(cmd, args);
        c.wait();
        int ret = c.exit_code();
        if (ret != 0)
        {
            std::cerr << "senspot-init returned nonzero exit code: " << ret << std::endl;
            exit(EXIT_FAILURE);
        }
        assert(ret == 0);
    }

    // TODO: how to get seqno from senspot_put?
    void senspot_put(const std::string &payload, const std::string &woof_addr)
    {

        std::cout << "[senspot.hpp] Issuing senspot-put for address " << woof_addr << std::endl;

        bp::pipe p;
        std::string echo_cmd = "/usr/bin/echo";
        bp::child echo_proc(echo_cmd, payload, bp::std_out > p);

        std::string senspot_put_cmd = senspot_dir + "/senspot-put";
        std::vector<std::string> args = {"-W", woof_addr, "-T", "s"};
        bp::child senspot_put_proc(senspot_put_cmd, args, bp::std_in < p);

        echo_proc.wait();
        int echo_ret = echo_proc.exit_code();
        if (echo_ret != 0)
        {
            std::cerr << "senspot-put: echo returned nonzero exit code: " << echo_ret << std::endl;
            exit(EXIT_FAILURE);
        }
        assert(echo_ret == 0);

        senspot_put_proc.wait();
        int put_ret = senspot_put_proc.exit_code();
        if (put_ret != 0)
        {
            std::cerr << "senspot-put returned nonzero exit code: " << put_ret << std::endl;
            exit(EXIT_FAILURE);
        }
        assert(put_ret == 0);
    }

    // This is a "thin" wrapper around the senspot-get binary in the sense that
    // it is up to the user application to parse the output as they see fit.
    // format: 3.140000 time: 1780951066.5463969707 192.168.101.30 seq_no: 1
    std::string senspot_get(const std::string &woof_addr)
    {
        std::string cmd = senspot_dir + "/senspot-get";
        std::vector<std::string> args = {"-W", woof_addr};
        bp::ipstream out;
        bp::child c(cmd, bp::args(args), bp::std_out > out);
        std::string output;
        std::string line;
        while (std::getline(out, line))
        {
            output += line;
        }
        c.wait();
        assert(c.exit_code() == 0);
        return output;
    }

    // TODO: implement
    // std::string senspot_get(const std::string &woof_addr, int seqno)
    // {
    //     return "";
    // }

  private:
    std::string senspot_dir;
};

#endif
