// Copyright (c) 2025-present The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_INDEX_KEY_H
#define BITCOIN_INDEX_KEY_H

#include <cstdint>
#include <string>
#include <stdexcept>
#include <utility>

static constexpr uint8_t DB_BLOCK_HASH{'s'};
static constexpr uint8_t DB_BLOCK_HEIGHT{'t'};

template<uint8_t Prefix, typename T, auto SerializeFunc, auto UnserializeFunc>
struct DBKey {
    T value;
    explicit DBKey(const T& v) : value(v) {}

    template<typename S>
    void Serialize(S& s) const {
        ser_writedata8(s, Prefix);
        SerializeFunc(s, value);
    }

    template<typename S>
    void Unserialize(S& s) {
        if (ser_readdata8(s) != Prefix)
            throw std::ios_base::failure("Invalid DB key prefix");
        UnserializeFunc(s, value);
    }
};

using DBHeightKey = DBKey<DB_BLOCK_HEIGHT, int,
        [](auto& s, int v) { ser_writedata32be(s, v); },
        [](auto& s, int& v) { v = ser_readdata32be(s); }>;

using DBHashKey = DBKey<DB_BLOCK_HASH, uint256,
        [](auto& s, const uint256& v) { ::Serialize(s, const_cast<uint256&>(v)); },
        [](auto& s, uint256& v) { ::Unserialize(s, v); }>;

template <typename DBVal>
[[nodiscard]] static bool CopyHeightIndexToHashIndex(CDBIterator& db_it, CDBBatch& batch,
                                                     const std::string& index_name, int height)
{
    DBHeightKey key(height);
    db_it.Seek(key);

    if (!db_it.GetKey(key) || key.value != height) {
        LogError("unexpected key in %s: expected (%c, %d)",
                  index_name, DB_BLOCK_HEIGHT, height);
        return false;
    }

    std::pair<uint256, DBVal> value;
    if (!db_it.GetValue(value)) {
        LogError("unable to read value in %s at key (%c, %d)",
                 index_name, DB_BLOCK_HEIGHT, height);
        return false;
    }

    batch.Write(DBHashKey(value.first), std::move(value.second));
    return true;
}

template <typename DBVal>
static bool LookUpOne(const CDBWrapper& db, const interfaces::BlockRef& block, DBVal& result)
{
    // First check if the result is stored under the height index and the value
    // there matches the block hash. This should be the case if the block is on
    // the active chain.
    std::pair<uint256, DBVal> read_out;
    if (!db.Read(DBHeightKey(block.height), read_out)) {
        return false;
    }
    if (read_out.first == block.hash) {
        result = std::move(read_out.second);
        return true;
    }

    // If value at the height index corresponds to an different block, the
    // result will be stored in the hash index.
    return db.Read(DBHashKey(block.hash), result);
}

#endif // BITCOIN_INDEX_KEY_H
