// Copyright (c) 2025-present The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <util/threadpool.h>

#include <test/fuzz/FuzzedDataProvider.h>
#include <test/fuzz/fuzz.h>

namespace {

    struct ExpectedException : std::runtime_error {
        using std::runtime_error::runtime_error;
    };

    struct MaybeThrowTask {
        bool m_should_throw{false};
        explicit MaybeThrowTask(const bool should_throw) : m_should_throw{should_throw} {}
        void operator()() const {
            if (m_should_throw) throw ExpectedException("fail");
        }
    };

    struct CounterTask {
        std::atomic_uint32_t& m_counter;
        explicit CounterTask(std::atomic_uint32_t& counter) : m_counter{counter} {}
        void operator()() const { m_counter.fetch_add(1); }
    };

} // namespace

FUZZ_TARGET(threadpool)
{
    FuzzedDataProvider fuzzed_data_provider(buffer.data(), buffer.size());

    const uint32_t num_tasks = fuzzed_data_provider.ConsumeIntegralInRange<uint32_t>(0, 1024);
    const uint32_t num_workers = fuzzed_data_provider.ConsumeIntegralInRange<uint32_t>(1, 16);
    ThreadPool pool{"fuzz_pool"};

    std::atomic_uint32_t task_counter{0};
    uint32_t expected_task_counter{0};
    std::vector<std::future<void>> futures;
    futures.reserve(num_tasks);
    pool.Start(num_workers);
    assert(pool.WorkersCount() == num_workers);
    assert(pool.WorkQueueSize() == 0);

    for (uint32_t i = 0; i < num_tasks; ++i) {
        bool will_throw = fuzzed_data_provider.ConsumeBool();
        bool wait_immediately = fuzzed_data_provider.ConsumeBool();

        std::future<void> fut;
        if (will_throw) {
            fut = pool.Submit(MaybeThrowTask{fuzzed_data_provider.ConsumeBool()});
        } else {
            fut = pool.Submit(CounterTask{task_counter});
        }

        if (!will_throw) ++expected_task_counter;

        // Only call get() once per future
        if (wait_immediately) {
            try { fut.get(); } catch (const ExpectedException&) {}
        } else {
            futures.push_back(std::move(fut));
        }
    }

    // Drain remaining futures
    for (auto& fut : futures) {
        try { fut.get(); } catch (const ExpectedException&) {}
    }

    assert(pool.WorkQueueSize() == 0);
    assert(task_counter == expected_task_counter);
}