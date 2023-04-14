// Copyright (c) 2021-2022 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_UTIL_THREAD_H
#define BITCOIN_UTIL_THREAD_H

#include <functional>
#include <future>
#include <string>

namespace util {
/**
 * A wrapper for do-something-once thread functions.
 */
void TraceThread(std::string_view thread_name, std::function<void()> thread_func);
/**
 * A wrapper for do-something-once thread functions with promise to track it.
 */
void TraceThreadAndTrack(std::string_view thread_name, std::function<void()> thread_func, std::promise<void> promise);

} // namespace util

#endif // BITCOIN_UTIL_THREAD_H
