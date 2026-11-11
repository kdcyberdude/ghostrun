// CPU reference build of the environment: the same per-env code as the GPU kernel, run on the host (OpenMP over
// envs). Used to check the GPU build bit for bit and for CPU-only tests.
// build: see rl/rlenv.py (build_cpu)
#include <cstdlib>
#include <cstring>
#include <exception>
#include <string>

#include "rlenv_api.h"
#include "rlenv_build.hpp"

namespace {

thread_local std::string g_error;

struct HostMem {
    std::vector<void*> blocks;
    void* alloc(std::size_t n) {
        void* p = std::aligned_alloc(64, (n + 63) / 64 * 64);
        if (!p) throw std::bad_alloc();
        blocks.push_back(p);
        return p;
    }
    void upload(void* dst, const void* src, std::size_t n) { std::memcpy(dst, src, n); }
    void zero(void* dst, std::size_t n) { std::memset(dst, 0, n); }
    ~HostMem() { for (void* p : blocks) std::free(p); }
};

struct Env {
    HostMem mem;
    rle::Built<HostMem> e;
};

// Every env of every game in one parallel loop (games finish at different speeds; dynamic scheduling balances them).
template <class F>
void each_env(Env& env, F&& f) {
    const int total = env.e.total;
    const auto& games = env.e.games;
#pragma omp parallel for schedule(dynamic, 1)
    for (int k = 0; k < total; ++k) {
        std::size_t gi = 0;
        while (k >= games[gi].offset + games[gi].n) ++gi;
        f(const_cast<rle::GameCtx&>(games[gi]), k - games[gi].offset);
    }
}

}  // namespace

extern "C" {

void* rlenv_create(int ngames, const int* game_ids, const std::uint8_t* const* roms, const std::size_t* rom_sizes,
                   const std::uint8_t* const* boot_pads, const std::size_t* boot_sizes, const int* n_envs,
                   std::uint64_t run_seed, int sticky, int idle_max, int dropout, int /*device*/) {
    try {
        std::vector<rle::GameSpec> specs;
        for (int i = 0; i < ngames; ++i)
            specs.push_back({game_ids[i], std::vector<std::uint8_t>(roms[i], roms[i] + rom_sizes[i]),
                             std::vector<std::uint8_t>(boot_pads[i], boot_pads[i] + boot_sizes[i]), n_envs[i]});
        auto* env = new Env();
        env->e = rle::build(env->mem, specs, run_seed, sticky, idle_max, dropout);
        return env;
    } catch (const std::exception& ex) {
        g_error = ex.what();
        return nullptr;
    }
}

int rlenv_num_envs(void* h) { return static_cast<Env*>(h)->e.total; }

void rlenv_bind(void* h, const std::int16_t* actions, std::uint8_t* obs, std::uint8_t* emph, float* reward,
                std::uint8_t* done, std::uint8_t* masks, std::uint8_t* timeline, std::uint8_t* pads,
                std::uint32_t* events, float* info) {
    auto& c = static_cast<Env*>(h)->e.common;
    c.actions = actions; c.obs = obs; c.emph = emph; c.reward = reward; c.done = done; c.masks = masks;
    c.timeline = timeline; c.pads = pads; c.events = events; c.info = info;
}

void rlenv_set_no_render(void* h, int v) { static_cast<Env*>(h)->e.common.no_render = v; }

void rlenv_bind_parts(void* h, float* parts) { static_cast<Env*>(h)->e.common.parts = parts; }

void rlenv_bind_obs(void* h, std::uint8_t* obs, std::uint8_t* emph) {
    auto& c = static_cast<Env*>(h)->e.common;
    c.obs = obs;
    c.emph = emph;
}

int rlenv_start(void* h, void*) {
    auto& env = *static_cast<Env*>(h);
    each_env(env, [&](rle::GameCtx& g, int i) {
        rle::Common c = env.e.common;
        if (g.bank_mode == 0) rle::env_start<nesle::cuda::kBankModeNrom>(g, c, i);
        else if (g.bank_mode == 2) rle::env_start<nesle::cuda::kBankModePaged>(g, c, i);
        else rle::env_start<nesle::cuda::kBankModeBanked>(g, c, i);
    });
    return 0;
}

int rlenv_step(void* h, void*) {
    auto& env = *static_cast<Env*>(h);
    each_env(env, [&](rle::GameCtx& g, int i) {
        rle::Common c = env.e.common;
        if (g.bank_mode == 0) rle::env_step<nesle::cuda::kBankModeNrom>(g, c, i);
        else if (g.bank_mode == 2) rle::env_step<nesle::cuda::kBankModePaged>(g, c, i);
        else rle::env_step<nesle::cuda::kBankModeBanked>(g, c, i);
    });
    // level-start saves (the GPU runs them after every env's ph_finish; restarts only read the saves in ph_finish)
    for (const auto& g : env.e.games)
        for (int s = 0; s < g.lv_cap; ++s) {
            if (g.lv_claim[s] == ~0ull) continue;
            const bool take = rle::archive_take(g, s);
            if (take) rle::archive_copy(g, s, 0, 1);
            rle::archive_commit(g, env.e.common, s, take);
        }
    return 0;
}

int rlenv_enable_level_starts(void* h, int cap) {
    try {
        auto& env = *static_cast<Env*>(h);
        rle::enable_level_starts(env.mem, env.e, cap);
        return 0;
    } catch (const std::exception& ex) {
        g_error = ex.what();
        return 1;
    }
}
void rlenv_set_level_plan(void* h, int gi, double p, const std::uint32_t* cdf) {
    auto& env = *static_cast<Env*>(h);
    rle::set_level_plan(env.mem, env.e, gi, p, cdf);
}
void rlenv_bind_start(void* h, std::int32_t* start_out) { static_cast<Env*>(h)->e.common.start_out = start_out; }
void rlenv_bind_level(void* h, std::int32_t* level_out) { static_cast<Env*>(h)->e.common.level_out = level_out; }
int rlenv_level_deaths(void* h, int gi, std::int32_t* out, void*) {
    const auto& g = static_cast<Env*>(h)->e.games[static_cast<std::size_t>(gi)];
    if (g.lv_cap) std::memcpy(out, g.lv_deaths, g.lv_cap * 4);
    return 0;
}

std::size_t rlenv_state_bytes(void* h) {
    std::size_t n = 0;
    rle::for_each_state(static_cast<Env*>(h)->e, [&](void*, std::size_t b) { n += b; });
    return n;
}

int rlenv_save(void* h, std::uint8_t* out, void*) {
    rle::for_each_state(static_cast<Env*>(h)->e, [&](void* p, std::size_t b) { std::memcpy(out, p, b); out += b; });
    return 0;
}

int rlenv_load(void* h, const std::uint8_t* in, void*) {
    rle::for_each_state(static_cast<Env*>(h)->e, [&](void* p, std::size_t b) { std::memcpy(p, in, b); in += b; });
    return 0;
}

const char* rlenv_error() { return g_error.c_str(); }

void rlenv_destroy(void* h) { delete static_cast<Env*>(h); }

}  // extern "C"
