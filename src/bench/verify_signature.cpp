// Copyright (c) 2026-present The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <bench/bench.h>
#include <common/ecc_init.h>
#include <key.h>
#include <pubkey.h>
#include <random.h>
#include <span.h>
#include <uint256.h>

#include <cassert>
#include <cstddef>
#include <span>
#include <vector>

// Note: verification is variable-time, so each iteration checks a different signature.

static constexpr size_t NUM_SIGS{32};

static CKey DeterministicKey(FastRandomContext& rng)
{
    const auto bytes{rng.randbytes<std::byte>(32)};
    CKey key;
    key.Set(bytes.begin(), bytes.end(), /*fCompressedIn=*/true);
    assert(key.IsValid());
    return key;
}

static void ECDSAVerify(benchmark::Bench& bench)
{
    const auto ecc_context{MakeContextECC()};
    FastRandomContext rng{/*fDeterministic=*/true};
    const CKey key{DeterministicKey(rng)};
    const CPubKey pubkey{key.GetPubKey()};
    std::vector<uint256> msgs;
    std::vector<std::vector<unsigned char>> sigs;
    for (size_t i{0}; i < NUM_SIGS; ++i) {
        msgs.push_back(rng.rand256());
        const bool ok{key.Sign(msgs.back(), sigs.emplace_back())};
        assert(ok);
    }

    size_t i{0};
    bench.minEpochIterations(200).run([&] {
        const bool valid{pubkey.Verify(msgs[i % NUM_SIGS], sigs[i % NUM_SIGS])};
        assert(valid);
        ++i;
    });
}

static void SchnorrVerify(benchmark::Bench& bench)
{
    const auto ecc_context{MakeContextECC()};
    FastRandomContext rng{/*fDeterministic=*/true};
    const CKey key{DeterministicKey(rng)};
    const XOnlyPubKey pubkey{key.GetPubKey()};
    const uint256 aux{rng.rand256()};
    std::vector<uint256> msgs;
    std::vector<std::vector<unsigned char>> sigs;
    for (size_t i{0}; i < NUM_SIGS; ++i) {
        msgs.push_back(rng.rand256());
        sigs.emplace_back(64);
        const bool ok{key.SignSchnorr(msgs.back(), sigs.back(), /*merkle_root=*/nullptr, aux)};
        assert(ok);
    }

    size_t i{0};
    bench.minEpochIterations(200).run([&] {
        const bool valid{pubkey.VerifySchnorr(msgs[i % NUM_SIGS], sigs[i % NUM_SIGS])};
        assert(valid);
        ++i;
    });
}

BENCHMARK(ECDSAVerify);
BENCHMARK(SchnorrVerify);
