// test_senspot.cpp
// Let's see if my senspot wrapper layer actually works.

// IMPORTANT NOTE: you need to copy the binary over into the same directory that
// the senspot binaries are located in order for this test script to work. I do
// not know why.

#include "../include/senspot.hpp"
#include <nlohmann/json.hpp>

using json = nlohmann::json;

int main(int argc, char **argv)
{

    // This is just for the sake of testing.
    for (int i = 0; i < argc; i++)
    {
        std::cout << argv[i] << std::endl;
    }

    senspot mynamespace("/home/pi/vinayak/iot-streaming/iot-streaming/bin");

    std::string woof_name = "mywoof";
    int woof_sz = 100;
    std::string woof_addr = "woof://127.0.0.1/home/pi/vinayak/iot-streaming/iot-streaming/bin/" + woof_name;

    mynamespace.senspot_init(woof_name, woof_sz);

    for (int i = 0; i < 10; i++)
    {
        json j;
        j["iter"] = std::to_string(i);
        j["payload"] =
            "The struggle itself toward the heights is enough to fill a man's heart. One must imagine Sisyphus happy.";
        mynamespace.senspot_put(j.dump(), woof_addr);
        std::string payload = mynamespace.senspot_get(woof_addr);
        std::cout << "Got: " << payload << std::endl;
    }
}
