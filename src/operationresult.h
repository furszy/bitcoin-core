// Copyright (c) 2022 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or https://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_OPERATIONRESULT_H
#define BITCOIN_OPERATIONRESULT_H

#include <optional>
#include <util/translation.h>

class OperationResult
{
private:
    bool m_res{false};
    std::optional<bilingual_str> m_error{std::nullopt};

public:
    OperationResult(bool _res, const bilingual_str& _error) : m_res(_res), m_error(_error) { }
    OperationResult(bool _res) : m_res(_res) { }

    bilingual_str GetError() const { return (m_error ? *m_error : bilingual_str()); }
    bool GetRes() const { return m_res; }
    explicit operator bool() const { return m_res; }
};

inline OperationResult ErrorOut(const bilingual_str& error_str)
{
    return OperationResult(false, error_str);
}


template <class T>
class CallResult : public OperationResult
{
private:
    std::optional<T> m_obj_res{std::nullopt};
public:
    CallResult() : OperationResult(false) {}
    CallResult(T _obj) : OperationResult(true), m_obj_res(_obj) { }
    CallResult(const bilingual_str& error) : OperationResult(false, error) { }
    const std::optional<T>& GetObjResult() const { return m_obj_res; }
};


#endif // BITCOIN_OPERATIONRESULT_H
