// Copyright (c) 2011-2022 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <compat/compat.h>
/**
 * See https://www.boost.org/doc/libs/1_78_0/libs/test/doc/html/boost_test/adv_scenarios/single_header_customizations/multiple_translation_units.html
 */
#define BOOST_TEST_NO_MAIN
#define BOOST_TEST_MAIN
#include <boost/test/included/unit_test.hpp>

MAIN_FUNCTION
{
    std::cout << "Running custom main function for tests!" << std::endl;
    bool result = false;
    try {
        ::boost::unit_test::framework::master_test_suite().p_name.value = "Bitcoin Core Test Suite";
        result = ::boost::unit_test::unit_test_main(&init_unit_test_suite, argc, argv);
    } catch (const std::exception& e) {
        std::cout << "Exception!" << std::endl;
        std::cout << "Uncaught exception: " << e.what() << std::endl;
        std::cerr << "Uncaught exception: " << e.what() << std::endl;
        exit(EXIT_FAILURE);
    } catch (...) {
        std::cout << "Catch all exceptions!" << std::endl;
    }
    return result;
}

#include <test/util/setup_common.h>

#include <functional>
#include <iostream>

/** Redirect debug log to unit_test.log files */
const std::function<void(const std::string&)> G_TEST_LOG_FUN = [](const std::string& s) {
    static const bool should_log{std::any_of(
        &boost::unit_test::framework::master_test_suite().argv[1],
        &boost::unit_test::framework::master_test_suite().argv[boost::unit_test::framework::master_test_suite().argc],
        [](const char* arg) {
            return std::string{"DEBUG_LOG_OUT"} == arg;
        })};
    if (!should_log) return;
    std::cout << s;
};

/**
 * Retrieve the command line arguments from boost.
 * Allows usage like:
 * `test_bitcoin --run_test="net_tests/cnode_listen_port" -- -checkaddrman=1 -printtoconsole=1`
 * which would return `["-checkaddrman=1", "-printtoconsole=1"]`.
 */
const std::function<std::vector<const char*>()> G_TEST_COMMAND_LINE_ARGUMENTS = []() {
    std::vector<const char*> args;
    for (int i = 1; i < boost::unit_test::framework::master_test_suite().argc; ++i) {
        args.push_back(boost::unit_test::framework::master_test_suite().argv[i]);
    }
    return args;
};

/**
 * Retrieve the boost unit test name.
 */
const std::function<std::string()> G_TEST_GET_FULL_NAME = []() {
    return boost::unit_test::framework::current_test_case().full_name();
};
