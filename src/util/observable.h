// Copyright (c) 2022 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or https://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_OBSERVABLE_H
#define BITCOIN_OBSERVABLE_H

#include <sync.h>
#include <set>

template <typename Observer>
class Observable {
private:
    Mutex m_cs;
    std::set<Observer*> m_observers;

public:
    void Register(Observer* ob) { WITH_LOCK(m_cs, m_observers.emplace(ob)); }
    void Unregister(Observer* ob) { WITH_LOCK(m_cs, m_observers.erase(ob)); }

    void Notify(std::function<void(Observer* ob)> func) {
        std::set<Observer*> obs = WITH_LOCK(m_cs, return m_observers);
        for (const auto& ob : obs) {
            if (ob) func(ob);
        }
    }
};


#endif //BITCOIN_OBSERVABLE_H
