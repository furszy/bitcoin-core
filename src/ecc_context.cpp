// Copyright (c) The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <ecc_context.h>

#include <crypto/sha256.h>
#include <secp256k1.h>

#include <cassert>
#include <span>
#include <type_traits>

/** Initialize elliptic curve context with our optimized SHA256 plugged in (see SHA256Transform).
 *  Provide rng seed for blinding factor if needed. */
static void ECC_Start(secp256k1_context*& ctx_inout, const std::span<const unsigned char>& rng_seed32) {
    assert(ctx_inout == nullptr);
    assert(rng_seed32.empty() || rng_seed32.size() == 32);

    secp256k1_context *ctx = secp256k1_context_create(SECP256K1_CONTEXT_NONE);
    assert(ctx != nullptr);

    if (!rng_seed32.empty()){
        // Pass in a random blinding seed to the secp256k1 context.
        bool ret = secp256k1_context_randomize(ctx, rng_seed32.data());
        assert(ret);
    }

    SHA256AutoDetect();
    static_assert(std::is_same_v<decltype(&SHA256Transform), secp256k1_sha256_compression_function>);
    secp256k1_context_set_sha256_compression(ctx, SHA256Transform);

    ctx_inout = ctx;
}

/** Deinitialize the elliptic curve context. No-op if ECC_Start wasn't called first. */
static void ECC_Stop(secp256k1_context*& ctx_inout) {
    secp256k1_context *ctx = ctx_inout;
    ctx_inout = nullptr;

    if (ctx) {
        secp256k1_context_destroy(ctx);
    }
}

ECC_Context::ECC_Context(const std::span<const unsigned char>& rng_seed32)
{
    ECC_Start(m_ctx, rng_seed32);
}

ECC_Context::~ECC_Context()
{
    ECC_Stop(m_ctx);
}
