// Copyright (c) 2026-present The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <crypto/sha256.h>
#include <ecc_context.h>
#include <hash.h>
#include <key.h>
#include <secp256k1.h>
#include <uint256.h>
#include <util/strencodings.h>

#include <boost/test/unit_test.hpp>

#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

BOOST_AUTO_TEST_SUITE(ecc_context_tests)

static bool CanSign()
{
    std::vector<unsigned char> sig;
    return GenerateRandomKey().Sign(uint256::ONE, sig);
}

BOOST_AUTO_TEST_CASE(sign_context_lifecycle)
{
    BOOST_CHECK(GetSecp256k1SignContext() == nullptr);
    {
        const auto ecc_context{MakeContextECC()};
        BOOST_CHECK(GetSecp256k1SignContext() != nullptr);
        BOOST_CHECK(GetSecp256k1SignContext() == ecc_context->SignContext());
        BOOST_CHECK(CanSign());
    }
    BOOST_CHECK(GetSecp256k1SignContext() == nullptr);
}

BOOST_AUTO_TEST_CASE(context_blinding_factor)
{
    // Check signatures do not depend on the blinding factor
    const auto sign{[](const CKey& sk, const std::span<const unsigned char> rng_seed32) {
        const ECC_Context ecc_context{rng_seed32};
        std::vector<unsigned char> sig;
        BOOST_REQUIRE(sk.Sign(uint256::ONE, sig));
        return sig;
    }};

    CKey key;
    constexpr std::array<unsigned char, 32> secret{1};
    key.Set(secret.begin(), secret.end(), /*fCompressedIn=*/true);
    constexpr std::array<unsigned char, 32> seed_a{2};
    constexpr std::array<unsigned char, 32> seed_b{3};
    BOOST_CHECK(sign(key, seed_a) == sign(key, seed_b));
    BOOST_CHECK(sign(key, seed_a) == sign(key, {}));
}

// Counts calls libsecp256k1 makes to the plugged compression function
int g_sha256_transform_calls{0};
void CountingSHA256Transform(uint32_t* state, const unsigned char* blocks64, size_t n_blocks)
{
    ++g_sha256_transform_calls;
    SHA256Transform(state, blocks64, n_blocks);
}

CKey TestKey()
{
    const auto secret{ParseHex("12b004fff7f4b69ef8650e767f18f11ede158148b425660723b9f9a66e61f747")};
    CKey key;
    key.Set(secret.begin(), secret.end(), /*fCompressedIn=*/true);
    BOOST_REQUIRE(key.IsValid());
    return key;
}
const uint256 TEST_MSG{Hash(std::string{"Very deterministic message"})};

BOOST_AUTO_TEST_CASE(sign_context_sha256)
{
    const auto ecc_context{MakeContextECC()};
    secp256k1_context* const ctx{GetSecp256k1SignContext()};

    const CKey key{TestKey()};
    const uint256 aux{uint256::ONE};
    const std::array<std::byte, 32> ent{};

    struct Outputs {
        std::vector<unsigned char> ecdsa, ecdsa_nogrind, compact, schnorr;
        EllSwiftPubKey ellswift;
        bool operator==(const Outputs& o) const
        {
            return ecdsa == o.ecdsa && ecdsa_nogrind == o.ecdsa_nogrind && compact == o.compact && schnorr == o.schnorr && ellswift == o.ellswift;
        }
    };
    const auto sign{[&] {
        Outputs out;
        BOOST_CHECK(key.Sign(TEST_MSG, out.ecdsa));
        BOOST_CHECK(key.Sign(TEST_MSG, out.ecdsa_nogrind, /*grind=*/false));
        BOOST_CHECK(key.SignCompact(TEST_MSG, out.compact));
        out.schnorr.resize(64);
        BOOST_CHECK(key.SignSchnorr(TEST_MSG, out.schnorr, /*merkle_root=*/nullptr, aux));
        out.ellswift = key.EllSwiftCreate(ent);
        return out;
    }};

    // Reference outputs with libsecp256k1's built-in SHA256, which the plug must not change; the
    // ECDSA one is the known answer from key_tests.
    secp256k1_context_set_sha256_compression(ctx, nullptr);
    const Outputs expected{sign()};
    BOOST_CHECK_EQUAL(HexStr(expected.ecdsa), "304402205dbbddda71772d95ce91cd2d14b592cfbc1dd0aabd6a394b6c2d377bbe59d31d022014ddda21494a4e221f0824f0b8b924c43fa43c0ad57dccdaa11f81a6bd4582f6");

    g_sha256_transform_calls = 0;
    secp256k1_context_set_sha256_compression(ctx, CountingSHA256Transform);
    BOOST_CHECK(sign() == expected);
    BOOST_CHECK_GT(g_sha256_transform_calls, 0);

    // Same outputs with each implementation the CPU supports (AVX2 has no single-block variant).
    secp256k1_context_set_sha256_compression(ctx, SHA256Transform);
    for (const auto impl : {sha256_implementation::STANDARD, sha256_implementation::USE_SSE4, sha256_implementation::USE_SSE4_AND_SHANI}) {
        BOOST_TEST_MESSAGE("SHA256 implementation: " << SHA256AutoDetect(impl));
        BOOST_CHECK(sign() == expected);
    }
    SHA256AutoDetect();
}

BOOST_AUTO_TEST_SUITE_END()
