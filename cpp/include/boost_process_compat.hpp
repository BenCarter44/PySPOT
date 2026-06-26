// boost_process_compat.hpp

// The Raspberry Pis have an older version of Boost installed than the one I
// have in my local development environment, and the header layout for
// boost::process changed slightly between those two versions. Regardless of
// which version your environment has installed, this header will make the "v1"
// API accessible under the "bp" namespace.

#ifndef PYSPOT_CPP_INCLUDE_BOOST_PROCESS_COMPAT_HPP
#define PYSPOT_CPP_INCLUDE_BOOST_PROCESS_COMPAT_HPP

#include <iostream>

// This is not a very robust check, but we'll assume that if this header is
// present, we are using the newer version of Boost. A more robust way would be
// to check the Boost version I think.
#if __has_include(<boost/process/v1/child.hpp>)

#include <boost/process/v1/args.hpp>
#include <boost/process/v1/child.hpp>
#include <boost/process/v1/io.hpp>
#include <boost/process/v1/system.hpp>

namespace bp = boost::process::v1;

#elif __has_include(<boost/process.hpp>)

#include <boost/process.hpp>

namespace bp = boost::process;

#endif

#endif
