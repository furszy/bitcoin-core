//
// Copyright (c) 2015-2018 The PIVX developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.
//

#include "GenWit.h"

GenWit::GenWit() {}

GenWit::GenWit(const CBloomFilter &filter, int startingHeight, libzerocoin::CoinDenomination den, int requestNum)
        : filter(filter), startingHeight(startingHeight), den(den), requestNum(requestNum) {}

bool GenWit::isValid(int chainActiveHeight) {
    if (den == libzerocoin::CoinDenomination::ZQ_ERROR){
        return false;
    }
    if(!filter.IsWithinSizeConstraints()){
        //TODO: throw exception
        return false;
    }
    return (startingHeight < chainActiveHeight - 20);
}

const CBloomFilter &GenWit::getFilter() const {
    return filter;
}

int GenWit::getStartingHeight() const {
    return startingHeight;
}

libzerocoin::CoinDenomination GenWit::getDen() const {
    return den;
}

int GenWit::getRequestNum() const {
    return requestNum;
}

CNode *GenWit::getPfrom() const {
    return pfrom;
}

void GenWit::setPfrom(CNode *pfrom) {
    GenWit::pfrom = pfrom;
}
