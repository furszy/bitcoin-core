//
// Copyright (c) 2015-2018 The PIVX developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.
//

#ifndef PIVX_LIGHTZPIVTHREAD_H
#define PIVX_LIGHTZPIVTHREAD_H

#include <atomic>
#include "GenWit.h"
#include "accumulators.h"
#include "concurrentqueue.h"
#include "chainparams.h"
#include "main.h"
#include <boost/function.hpp>
#include <boost/thread.hpp>

extern CChain chainActive;

/****** Thread ********/

class LightWorker{

private:

    concurrentqueue<GenWit> requestsQueue;
    volatile std::atomic<bool> isWorkerRunning;
    boost::thread threadIns;

public:

    LightWorker() {
        isWorkerRunning = false;
    }

    bool addWitWork(GenWit wit) {
        if (!isWorkerRunning) {
            return false;
        }
        requestsQueue.push(wit);
        return true;
    }

    void StartLightZpivThread(boost::thread_group& threadGroup){
        LogPrintf("%s thread start\n", "pivx-light-thread");
        threadIns = boost::thread(boost::bind(&LightWorker::ThreadLightZPIV, this));
    }

    void StopLightZpivThread(){
        threadIns.interrupt();
        LogPrintf("%s thread interrupted\n", "pivx-light-thread");
    }

private:

    void ThreadLightZPIV(){
        RenameThread("pivx-light-thread");
        isWorkerRunning = true;
        while (true) {
            try {
                std::cout << "loop light" << std::endl;

                list<GenWit> requests;
                libzerocoin::CoinDenomination den = libzerocoin::CoinDenomination::ZQ_ERROR;

                std::cout << "before pop" << std::endl;
                GenWit genWit = requestsQueue.pop();

                requests.push_back(genWit);
                den = genWit.getDen();

                // wait 500 millis for more requests before continue
                MilliSleep(500);

                list<GenWit> notAddedRequests;
                while (requestsQueue.hasElements()) {
                    GenWit wit = requestsQueue.popNotWait();
                    if (genWit.getDen() == den) {
                        requests.push_back(wit);
                    } else{
                        notAddedRequests.push_back(wit);
                    }
                }

                // Merge requests
                CBloomFilter filter;
                int startingHeight = 0;
                if (!requests.empty()) {
                    int n = 0;
                    for (const GenWit wit : requests) {
                        if (n == 0) {
                            filter = wit.getFilter();
                            startingHeight = wit.getStartingHeight();
                        } else {
                            if(filter.Merge(wit.getFilter())){
                                if (startingHeight < wit.getStartingHeight()){
                                    startingHeight = wit.getStartingHeight();
                                }
                            }else{
                                notAddedRequests.push_back(wit);
                            }

                        }
                        n++;
                    }
                }

                // Not added values
                for (GenWit wit : notAddedRequests){
                    requestsQueue.push(wit);
                }

                //if (requests.empty()){
                //    std::cout << "requests empty? " << std::endl;
                //}

                GenWit gen(filter, startingHeight, den, -1);
                // Filter good
                std::cout << "filter good, starting height: " << gen.getStartingHeight() << std::endl;
                libzerocoin::ZerocoinParams *params = Params().Zerocoin_Params(false);
                CBlockIndex *pIndex = chainActive[gen.getStartingHeight()];
                if (!pIndex) {
                    // TODO: Si falla lo que tengo que hacer es devolver todos al queue menos el que tiene el height que falló (o sea el menor) que le envio un mensaje de error
                    // Return something..
                    std::cout << "Min height to spend a zpiv is 20" << std::endl;
                    for (GenWit wit : requests) {
                        CDataStream ss(SER_NETWORK, PROTOCOL_VERSION);
                        // Invalid request only returns the message without a result.
                        ss << wit.getRequestNum();
                        wit.getPfrom()->PushMessage("pubcoins", ss);
                    }
                } else {
                    int blockHeight = pIndex->nHeight;
                    std::cout << "Block start: " << blockHeight << std::endl;
                    if (blockHeight != 0) {

                        libzerocoin::Accumulator accumulator(params, gen.getDen());
                        libzerocoin::PublicCoin temp(params);
                        libzerocoin::AccumulatorWitness witness(params, accumulator, temp);
                        string strFailReason = "";
                        int nMintsAdded = 0;
                        CZerocoinSpendReceipt receipt;

                        list<CBigNum> ret;

                        bool res = GenerateAccumulatorWitnessFor(
                                params,
                                blockHeight,
                                gen.getDen(),
                                gen.getFilter(),
                                accumulator,
                                witness,
                                100,
                                nMintsAdded,
                                strFailReason,
                                ret
                        );

                        std::cout << "genWit " << res << std::endl;
                        std::cout << "Amount of not added coins: " << ret.size() << std::endl;
                        std::cout << "Amount of added coins: " << nMintsAdded << std::endl;
                        std::cout << "acc: " << accumulator.getValue().GetDec() << std::endl;
                        std::cout << "generated witness: " << witness.getValue().GetDec() << std::endl;

                        for (GenWit wit : requests){
                            CDataStream ss(SER_NETWORK, PROTOCOL_VERSION);
                            ss.reserve(ret.size() * 32);

                            ss << wit.getRequestNum();
                            ss << accumulator.getValue();
                            ss << witness.getValue();
                            uint32_t size = ret.size();
                            ss << size;
                            std::cout << "ret size: " << size << std::endl;
                            std::cout << "request num: " << wit.getRequestNum() << std::endl;
                            for (CBigNum bnValue : ret) {
                                ss << bnValue;
                            }
                            //std::cout << "just about to send the message " << std::endl;
                            if (wit.getPfrom()) {
                                wit.getPfrom()->PushMessage("pubcoins", ss);
                                //std::cout << "Message pushed";
                            }else{
                                std::cout << "pfrom null " << std::endl;
                            }
                        }
                    }else {
                        // TODO: reject only the failed height
                        for (GenWit wit : requests) {
                            CDataStream ss(SER_NETWORK, PROTOCOL_VERSION);
                            // Invalid request only returns the message without a result.
                            ss << wit.getRequestNum();
                            wit.getPfrom()->PushMessage("pubcoins", ss);
                        }
                    }
                }
                //std::cout << "Finishing loop" << std::endl;
            }catch (std::exception& e) {
                std::cout << "exception in light loop, closing it. " << e.what() << std::endl;
                PrintExceptionContinue(&e, "lightzpivthread");
                break;
            }
        }
    }

};

#endif //PIVX_LIGHTZPIVTHREAD_H
