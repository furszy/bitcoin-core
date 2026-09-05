// Copyright (c) 2026-present The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <ecc_context.h>
#include <key.h>
#include <uint256.h>

#include <boost/test/unit_test.hpp>

#include <array>
#include <span>
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

BOOST_AUTO_TEST_SUITE_END()
