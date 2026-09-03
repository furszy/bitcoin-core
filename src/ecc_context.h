// Copyright (c) The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_ECC_CONTEXT_H
#define BITCOIN_ECC_CONTEXT_H

#include <span>

struct secp256k1_context_struct;
typedef struct secp256k1_context_struct secp256k1_context;

/**
 * RAII class initializing and deinitializing global state for elliptic curve support.
 * Only one instance may be initialized at a time.
 *
 * In the future global ECC state could be removed, and this class could contain
 * state and be passed as an argument to ECC key functions.
 */
class ECC_Context
{
public:
    explicit ECC_Context(const std::span<const unsigned char>& rng_seed32);
    ECC_Context(const ECC_Context&) = delete;
    ECC_Context& operator=(const ECC_Context&) = delete;

    ~ECC_Context();

    secp256k1_context* GetCtx() const { return m_ctx; }

private:
    secp256k1_context* m_ctx;
};


#endif //BITCOIN_ECC_CONTEXT_H
