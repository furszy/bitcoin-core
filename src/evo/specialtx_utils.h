// Copyright (c) 2022 The PIVX Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or htts://www.opensource.org/licenses/mit-license.php.

#ifndef PIVX_SPECIALTX_UTILS_H
#define PIVX_SPECIALTX_UTILS_H

#include "operationresult.h"
#include "primitives/transaction.h"

template<typename SpecialTxPayload>
static void UpdateSpecialTxInputsHash(const CMutableTransaction& tx, SpecialTxPayload& payload)
{
    payload.inputsHash = CalcTxInputsHash(tx);
}

#ifdef ENABLE_WALLET

class CWallet;
struct CMutableTransaction;

OperationResult FundSpecialTx(CWallet* pwallet, CMutableTransaction& tx);

template<typename SpecialTxPayload>
OperationResult FundSpecialTx(CWallet* pwallet, CMutableTransaction& tx, SpecialTxPayload& payload)
{
    SetTxPayload(tx, payload);
    auto res = FundSpecialTx(pwallet, tx);
    if (res) UpdateSpecialTxInputsHash(tx, payload);
    return res;
}

#endif // ENABLE_WALLET

#endif //PIVX_SPECIALTX_UTILS_H
