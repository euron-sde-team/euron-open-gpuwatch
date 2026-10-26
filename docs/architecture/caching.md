# Caching

The caching layers of GPUWatch (what is cached, where, the key design, the TTL, the
invalidation trigger and the tests that prove invalidation) are documented in one place:
[HLD.md, Caching layers](HLD.md#caching-layers). The dashboard's React Query `staleTime`
values referenced from `apps/web/src/lib/query-keys.ts` are listed in the same table.
