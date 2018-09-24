// Copyright (c) 2015-2018 The PIVX developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef PIVX_GENWIT_H
#define PIVX_GENWIT_H


#include "bloom.h"
#include "libzerocoin/Denominations.h"
#include "net.h"

class GenWit {

    public:

    GenWit();

    GenWit(const CBloomFilter &filter, int startingHeight, libzerocoin::CoinDenomination den, int requestNum);

    bool isValid(int chainActiveHeight);

    ADD_SERIALIZE_METHODS;
    template <typename Stream, typename Operation>
    inline void SerializationOp(Stream& s, Operation ser_action, int nType, int nVersion) {
        READWRITE(filter);
        filter.setFull();
        READWRITE(startingHeight);
        READWRITE(den);
        READWRITE(requestNum);
    }

    const CBloomFilter &getFilter() const;

    int getStartingHeight() const;

    libzerocoin::CoinDenomination getDen() const;

    int getRequestNum() const;

    CNode *getPfrom() const;

    void setPfrom(CNode *pfrom);

private:
    CBloomFilter filter;
    int startingHeight;
    libzerocoin::CoinDenomination den;
    int requestNum;
    CNode* pfrom;

};


#endif //PIVX_GENWIT_H
