// str.hpp
// C++ std::string utility functions that I find myself using in every project.
// Original source: https://github.com/vinayakgajjewar/spatial-dht/blob/main/src/str.cpp

#ifndef PYSPOT_CPP_INCLUDE_STR_HPP
#define PYSPOT_CPP_INCLUDE_STR_HPP

#include <sstream>

namespace str
{
std::string trim(const std::string &s)
{
    auto begin = std::find_if_not(s.begin(), s.end(), [](char c) { return std::isspace(c); });
    auto end = std::find_if_not(s.rbegin(), s.rend(), [](char c) { return std::isspace(c); }).base();
    if (begin >= end)
    {
        return {};
    }
    return std::string(begin, end);
}
std::vector<std::string> split(const std::string &s, char delim)
{
    if (s.empty())
        return {};
    std::vector<std::string> splits;
    std::string curr;
    std::istringstream iss(s);
    while (std::getline(iss, curr, delim))
    {
        curr = trim(curr);
        if (!curr.empty())
            splits.push_back(curr);
    }
    return splits;
}
} // namespace str

#endif
