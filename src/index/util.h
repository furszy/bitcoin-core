// Copyright (c) 2022 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or https://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_INDEX_UTIL_H
#define BITCOIN_INDEX_UTIL_H

#include <node/interface_ui.h>
#include <shutdown.h>
#include <tinyformat.h>
#include <warnings.h>

#include <string>

constexpr auto SYNC_LOG_INTERVAL{30s};
constexpr auto SYNC_LOCATOR_WRITE_INTERVAL{30s};

template <typename... Args>
static void FatalError(const char* fmt, const Args&... args)
{
    std::string strMessage = tfm::format(fmt, args...);
    SetMiscWarning(Untranslated(strMessage));
    LogPrintf("*** %s\n", strMessage);
    AbortError(_("A fatal internal error occurred, see debug.log for details"));
    StartShutdown();
}

#endif // BITCOIN_INDEX_UTIL_H
