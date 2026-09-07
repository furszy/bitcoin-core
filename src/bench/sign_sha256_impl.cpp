// Copyright (c) 2026-present The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <bench/bench.h>
#include <common/ecc_init.h>
#include <crypto/sha256.h>
#include <ecc_context.h>
#include <key.h>
#include <random.h>
#include <secp256k1.h>
#include <tinyformat.h>
#include <uint256.h>

#include <cassert>
#include <cstddef>
#include <optional>
#include <span>
#include <string>
#include <vector>

// Signing with each SHA256 implementation plugged into libsecp256k1, against its built-in one.
// Nothing in the timed loops hashes on our side, and every variant signs the same messages.

// Selects the SHA256 used by the signing context, one of ours or libsecp256k1's built-in for
// nullopt, and returns its name.
static std::string SelectSHA256(std::optional<sha256_implementation::UseImplementation> impl)
{
    const std::string name{impl ? SHA256AutoDetect(*impl) : "libsecp256k1 built-in"};
    secp256k1_context_set_sha256_compression(GetSecp256k1SignContext(), impl ? SHA256Transform : nullptr);
    return name;
}

static CKey DeterministicKey(FastRandomContext& rng)
{
    const auto bytes{rng.randbytes<std::byte>(32)};
    CKey key;
    key.Set(bytes.begin(), bytes.end(), /*fCompressedIn=*/true);
    assert(key.IsValid());
    return key;
}

static void ECDSASign(benchmark::Bench& bench, const char* bench_name, std::optional<sha256_implementation::UseImplementation> impl)
{
    const auto ecc_context{MakeContextECC()};
    bench.name(strprintf("%s using the '%s' SHA256 implementation", bench_name, SelectSHA256(impl)));

    FastRandomContext rng{/*fDeterministic=*/true};
    const CKey key{DeterministicKey(rng)};
    uint256 msg;
    std::vector<unsigned char> sig;

    bench.minEpochIterations(200).run([&] {
        msg = rng.rand256(); // new message each time so low-R grinding takes ~2 attempts on average
        const bool ok{key.Sign(msg, sig)};
        assert(ok);
    });
    SHA256AutoDetect();
}

static void SchnorrSign(benchmark::Bench& bench, const char* bench_name, std::optional<sha256_implementation::UseImplementation> impl)
{
    const auto ecc_context{MakeContextECC()};
    bench.name(strprintf("%s using the '%s' SHA256 implementation", bench_name, SelectSHA256(impl)));

    FastRandomContext rng{/*fDeterministic=*/true};
    const KeyPair keypair{DeterministicKey(rng).ComputeKeyPair(/*merkle_root=*/nullptr)};
    const uint256 aux{rng.rand256()};
    uint256 msg;
    std::vector<unsigned char> sig(64);

    bench.minEpochIterations(200).run([&] {
        msg = rng.rand256();
        const bool ok{keypair.SignSchnorr(msg, sig, aux)};
        assert(ok);
    });
    SHA256AutoDetect();
}

static void ECDSASign_SECP256K1(benchmark::Bench& bench) { ECDSASign(bench, __func__, std::nullopt); }
static void ECDSASign_STANDARD(benchmark::Bench& bench) { ECDSASign(bench, __func__, sha256_implementation::STANDARD); }
static void ECDSASign_SSE4(benchmark::Bench& bench) { ECDSASign(bench, __func__, sha256_implementation::USE_SSE4); }
static void ECDSASign_SHANI(benchmark::Bench& bench) { ECDSASign(bench, __func__, sha256_implementation::USE_SSE4_AND_SHANI); }

static void SchnorrSign_SECP256K1(benchmark::Bench& bench) { SchnorrSign(bench, __func__, std::nullopt); }
static void SchnorrSign_STANDARD(benchmark::Bench& bench) { SchnorrSign(bench, __func__, sha256_implementation::STANDARD); }
static void SchnorrSign_SSE4(benchmark::Bench& bench) { SchnorrSign(bench, __func__, sha256_implementation::USE_SSE4); }
static void SchnorrSign_SHANI(benchmark::Bench& bench) { SchnorrSign(bench, __func__, sha256_implementation::USE_SSE4_AND_SHANI); }

// Dominated by libsecp256k1's self-tests of the plugged function.
static void ECCContextCreate(benchmark::Bench& bench)
{
    bench.run([&] {
        const auto ecc_context{MakeContextECC()};
    });
}

BENCHMARK(ECDSASign_SECP256K1);
BENCHMARK(ECDSASign_STANDARD);
BENCHMARK(ECDSASign_SSE4);
BENCHMARK(ECDSASign_SHANI);
BENCHMARK(SchnorrSign_SECP256K1);
BENCHMARK(SchnorrSign_STANDARD);
BENCHMARK(SchnorrSign_SSE4);
BENCHMARK(SchnorrSign_SHANI);
BENCHMARK(ECCContextCreate);
