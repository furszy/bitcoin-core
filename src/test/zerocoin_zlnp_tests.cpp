#include "amount.h"
#include "chainparams.h"
#include "main.h"
#include "wallet.h"
#include "walletdb.h"
#include "txdb.h"
#include <boost/test/unit_test.hpp>
#include <iostream>
#include <time.h>


using namespace libzerocoin;

// ----- COLORS -----
#define COLOR_STR_NORMAL  "\033[0m"
#define COLOR_BOLD        "\033[1m"
#define COLOR_STR_GREEN   "\033[32m"
#define COLOR_STR_RED     "\033[31m"
#define COLOR_CYAN        "\033[0;36m"
#define COLOR_MAGENTA     "\u001b[35m"

std::string colorNormal(COLOR_STR_NORMAL);
std::string colorBold(COLOR_BOLD);
std::string colorGreen(COLOR_STR_GREEN);
std::string colorRed(COLOR_STR_RED);
std::string colorCyan(COLOR_CYAN);
std::string colorMagenta(COLOR_MAGENTA);


// Global test counters
uint32_t    zNumTests        = 0;
uint32_t    zSuccessfulTests = 0;


// ----- Serialization -----
bool Test_mintSerialization(const CTxOut& txout)
{
    zNumTests++;
    std::cout << "- Testing mint serialization...";
    vector<unsigned char> data1, data2;

    // Old code
    CBigNum publicZerocoin;
    vector<unsigned char> vchZeroMint;
    vchZeroMint.insert(vchZeroMint.end(), txout.scriptPubKey.begin() + 6, txout.scriptPubKey.begin() + txout.scriptPubKey.size());
    publicZerocoin.setvch(vchZeroMint);
    data1 = publicZerocoin.getvch();

    // New code
    data2 = vector<unsigned char>(txout.scriptPubKey.begin() + 6, txout.scriptPubKey.begin() + txout.scriptPubKey.size());

    // Test for equality
    if ( data1 != data2 ) {
        // Test Failed
        std::cout << colorRed << "FAIL" << std::endl;
        std::cout << "data1 = " << std::endl;
        for(unsigned char c : data1) std::cout << " " << std::hex << (int)c;
        std::cout << std::endl << "data2 = " << std::endl;
        for(unsigned char c : data2) std::cout << " " << std::hex << (int)c;
        std::cout << std::endl << colorNormal << std::endl;
        return false;
    }
    // Test Passed
    std::cout << colorGreen << "PASS" << colorNormal << std::endl;
    zSuccessfulTests++;
    return true;
}


CBigNum ParseSerial_old(CDataStream& s){
    unsigned int nSize = ReadCompactSize(s);
    s.movePos(nSize);
    nSize = ReadCompactSize(s);
    s.movePos(nSize);
    CBigNum coinSerialNumber;
    s >> coinSerialNumber;
    return coinSerialNumber;
}


bool Test_spendSerialization(const CTxIn& txin)
{
    zNumTests++;
    std::cout << "- Testing spend serialization...";
    vector<unsigned char> data1, data2;

    // Old code
    std::vector<char, zero_after_free_allocator<char> > spend;
    spend.insert(spend.end(), txin.scriptSig.begin() + 44, txin.scriptSig.end());
    CDataStream s(spend, SER_NETWORK, PROTOCOL_VERSION);
    CBigNum serial = ParseSerial_old(s);
    data1 = serial.getvch();

    // New code
    CDataStream s2(vector<unsigned char>(txin.scriptSig.begin() + 44, txin.scriptSig.end()), SER_NETWORK, PROTOCOL_VERSION);
    data2 = libzerocoin::CoinSpend::ParseSerial(s2);

    // Test for equality
    if ( data1 != data2 ) {
        // Test Failed
        std::cout << colorRed << "FAIL" << std::endl;
        std::cout << "data1 = " << std::endl;
        for(unsigned char c : data1) std::cout << " " << std::hex << (int)c;
        std::cout << std::endl << "data2 = " << std::endl;
        for(unsigned char c : data2) std::cout << " " << std::hex << (int)c;
        std::cout << std::endl << colorNormal << std::endl;
        return false;
    }
    // Test Passed
    std::cout << colorGreen << "PASS" << colorNormal << std::endl;
    zSuccessfulTests++;
    return true;
}



bool serialization_tests()
{
    std::cout << colorBold << "*** serialization_tests ***" << std::endl;
    std::cout << "------------------------" << colorNormal << std::endl;

    bool finalResult = true;

    // get zerocoin mint tx output
    SelectParams(CBaseChainParams::MAIN);
    ZerocoinParams *ZCParams = Params().Zerocoin_Params(false);
    (void)ZCParams;
    CBigNum msghash = CBigNum::randBignum(256);
    PrivateCoin newCoin(ZCParams, CoinDenomination::ZQ_ONE);
    PublicCoin pubCoin = newCoin.getPublicCoin();
    Commitment commitment(&(ZCParams->serialNumberSoKCommitmentGroup), pubCoin.getValue());

    CScript scriptSerializedCoin = CScript() << OP_ZEROCOINMINT << pubCoin.getValue().getvch().size() << pubCoin.getValue().getvch();
    CTxOut outMint = CTxOut(libzerocoin::ZerocoinDenominationToAmount(CoinDenomination::ZQ_ONE), scriptSerializedCoin);

    finalResult = finalResult & Test_mintSerialization(outMint);
    std::cout << std::endl;

    // get zerocoin spend tx input
    CZerocoinSpendReceipt receipt;
    CZerocoinMint mint  = CZerocoinMint(CoinDenomination::ZQ_ONE, pubCoin.getValue(), newCoin.getRandomness(), newCoin.getSerialNumber(), false, 2);
    uint256 hashTxOut = CBigNum::randBignum(256).getuint256();
    CTxIn inSpend;
    // -- accumulator
    libzerocoin::PublicCoin pubCoinSelected(ZCParams, mint.GetValue(), mint.GetDenomination());
    libzerocoin::Accumulator accumulator(ZCParams, mint.GetDenomination());
    libzerocoin::AccumulatorWitness witness(ZCParams, accumulator, pubCoinSelected);
    accumulator += pubCoinSelected;
    // -- coinspend
    uint32_t nChecksum = GetChecksum(accumulator.getValue());
    libzerocoin::CoinSpend spend(ZCParams, ZCParams, newCoin, accumulator, nChecksum, witness, hashTxOut, libzerocoin::SpendType::SPEND);
    CDataStream serializedCoinSpend(SER_NETWORK, PROTOCOL_VERSION);
    serializedCoinSpend << spend;
    std::vector<unsigned char> data(serializedCoinSpend.begin(), serializedCoinSpend.end());
    // -- TxIn
    inSpend.scriptSig = CScript() << OP_ZEROCOINSPEND << data.size();
    inSpend.scriptSig.insert(inSpend.scriptSig.end(), data.begin(), data.end());
    inSpend.prevout.SetNull();

    finalResult = finalResult & Test_spendSerialization(inSpend);
    std::cout << std::endl;

    return finalResult;
}



BOOST_AUTO_TEST_SUITE(zerocoin_zlnp_tests)

BOOST_AUTO_TEST_CASE(zlnp_tests)
{
    std::cout << std::endl;
    BOOST_CHECK(serialization_tests());
    std::cout << std::endl << zSuccessfulTests << " out of " << zNumTests << " tests passed." << std::endl << std::endl;
}
BOOST_AUTO_TEST_SUITE_END()
