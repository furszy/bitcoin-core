#ifndef SECP256K1_SHA_H
#define SECP256K1_SHA_H

#include "secp256k1.h"

#include <stdint.h>

/**
 * SHA-256 block compression routine.
 *
 * Updates the 8-word `state` by running the standard SHA-256 transform over
 * `rounds` consecutive 64-byte blocks starting at `msg`. This is the raw
 * block-level primitive: no padding, no length encoding, nothing beyond the
 * compression function itself.
 *
 * Callers must provide fully-formed, block-aligned input.
 *
 * @param state   Current hash state (8 x 32-bit words), updated in place.
 * @param msg     Pointer to a 64-byte message block.
 * @param rounds  How many times to re-run the transform on the same 64-byte block.
 */
SECP256K1_API void secp256k1_sha256_transform(
        uint32_t *state,
        const unsigned char *msg,
        size_t rounds
) SECP256K1_ARG_NONNULL(1) SECP256K1_ARG_NONNULL(2);

#endif /* SECP256K1_SHA_H */
