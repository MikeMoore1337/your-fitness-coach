"""Pinned cost-balanced, complete pytest shard planning for required CI.

The 200 most expensive nodeid hashes were measured on the identical
PR HEAD 0cb0298d8766ce8542377a7ea041f9dbb31bf4f7 in successful
GitHub Actions runs 42750264964, 42759750293 and 42775094876.
Each number is the median milliseconds of setup + call + teardown.
Unseen tests use a 2300 ms estimate, never disappear from a shard.
The timings estimate workload, not runner/CI wall time or an achieved SLO.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

_DIGEST = re.compile(r"[0-9a-f]{64}\\Z")
_PREFIX = re.compile(r"[0-9a-f]{16}\\Z")
_UNKNOWN_COST_MS = 2300
_RECORDED_COST_LINES = """1efec5b508d3bd9a 18840
c4e8e1cf35e6b70f 15716
2462968bd87b14be 13646
a52566dfa490ce25 13388
190814867c84cbdb 11597
d42f9a9acf95f864 11406
0903503427b32e01 9702
7c4f5578706dafc5 9658
401cada1f6cbbc22 9212
9910016b5e3736bc 8947
02e261e5d7b9f330 8897
1ce80f6ee2c2edcf 8439
f8a6fe2e97d63d36 8220
c43ba4ed2e374b3e 7816
298ba5e22d473323 7805
e771b3e6b8bd2d02 7759
a317a88cc1daba8c 7700
f93f6898d7c4ff6e 7525
e39cfd5550d35cf9 7456
a0df18b1e2778245 7339
586e006868fc44d8 7305
c464b62376c73db5 7252
0cc99e09e2199de9 7240
cc8da4f8927a48f5 7235
e42b400ee73fc7b6 7232
787b71d2de9380d9 7177
55667c0b301cce5c 7125
cf800427e35a987f 7088
3c222a31eb3cdd8a 7040
a8f4d4bea854985f 7019
9e76ba6f085cc35b 7012
dd3a604bb21d48d6 6978
b4efbcebd81a4bc1 6961
131e88d7a23ed7e8 6897
889b548fc671487e 6837
77b2557c3524b487 6795
8046cac58c55c83a 6687
101322003886042a 6644
5f473261f3cd207f 6633
895bea5bbc8a268c 6601
fb2e2b1f4d546790 6585
336be0a213453a0c 6569
37e40bdbfab12434 6569
ef3de3ee63542a1d 6542
ad0b9dc4a29b9634 6481
241166616ef027f0 6473
24f62ebfaf0e0585 6435
30cd59a0e6989ad9 6388
fcdebce046903315 6365
033fac42fb94e054 6355
a7f2f830c3b66cc6 6354
5f75a89f57898d18 6286
3da8b6a5e4de6e25 6268
8ab2a3607d7b02dd 6252
dfa0b6954ec95131 6187
e7b69f3547aa1166 6092
0c7648d393cee5f4 6081
2a9e741ae58d18d0 6077
f2946c0008c8d871 6049
71554a291a9d89de 5979
4cb39b2d7a5f6082 5976
2a255eff3ca48eb6 5765
a328a2ca248aa0b7 5763
977402a2e6b80e7d 5612
aba1c193019a4860 5604
f8b92516bdc768f3 5508
57bc0c138be4cc84 5371
caea4d756cd07daa 5335
72039af88b1af4a1 5284
1ea07e26b6c2df0e 5271
8a5397e7fb4f482e 5270
9f29387b1dd1e683 5259
04caccd921e567cd 5257
7673f2318e6a1afb 5201
dc2a264265604a57 5188
7a58ff5ae7a852f6 5148
e1ce93bac8c04ee0 5144
4dc995dc7350d26e 5133
3f74456c5b137c87 5078
3bee2a3612d90945 5021
ed366d62590b8065 4960
0f1ca488b1e564fc 4912
b8dccd93c8fabc19 4900
202b99a891a55ec1 4890
7255b6552a81c999 4878
5c84fee3ac105b49 4870
22f15b0414193cea 4839
80f5c14a16e6e5e6 4828
307ef8df182ff113 4794
190e5440ac38a937 4739
e061f60d05c2cc4b 4711
4d8704f15f1df86a 4710
c497cfb8a7ddb04f 4665
b977027754be515f 4663
349714f9adfc5476 4656
b7976bcbf7e88e28 4645
dab121e505284dbb 4624
02d6ade2321f75b9 4611
b24c92cff32d37f8 4607
171dbc5fcd3b8c9b 4583
66b4c606ca0f3007 4578
d59f9c9181867c0b 4555
179e82142b5ce1aa 4538
e5b04b6a148cd1fa 4528
1e7c6852ce56a041 4477
0e7d07edc80162dd 4463
f6f042fb97e6c07a 4427
ea46c97501152462 4418
99c283631d5a0e9b 4404
f36050ee6c9758e5 4393
9e6c3852d67d07d0 4378
956827d3216526a2 4377
9f2e9df1dee3c284 4371
578a009d71334f35 4362
3ac6a686abd7b39c 4349
ace5ff2beae82073 4324
130adb2bb00c0e39 4308
e72e0648a5e109ec 4306
e91a16ea803f0a80 4305
451a55b63b011357 4272
54ce111457284722 4268
c72d81a62b1c7189 4253
fee61f6fa5d0e6af 4217
b1a4254a013ce455 4188
863c6281f4dd8fa8 4185
1065ba33adcaab48 4149
d090835ee19e7b15 4148
77638ee5e448e542 4139
5bc9f4a6cc59c502 4138
568a5f1d9f9444c7 4126
b25b061bcc31519f 4119
c3a70476dbbef469 4115
ee07a62089f6381d 4094
2ac3012b6a80c748 4083
d9fc5ff52207ea56 4081
75466219b86781c1 4075
818b4a62a074559a 4070
ec558af910f34d31 4067
0e3e1df97621b718 4063
735d8cff38f91341 4058
03afd96a217c3892 4027
18148bd3c85386d1 4012
77038a0e4e09cd6c 4010
91598b945743b4d1 4008
ce024b99bb2397da 4004
1fcd11824a4aa780 3995
852c587df0c4ac05 3985
49c8e45718b58b0b 3974
62677662d0db3fbf 3970
ece52af239bfec51 3970
c1cdf323d8fa608f 3962
815d8018932c976f 3956
4f57f73322a204a6 3955
9829ad767637e48f 3950
08cb95286c258ece 3949
945ccf1c5c6f62a4 3946
232596fdde3bd453 3942
6f9eaae2f1ce09f7 3930
f9f582d22acdfb28 3928
aa02ff79d570fb88 3922
f8a900045b4bde72 3921
f60c7aa5a878dffa 3913
20c320feace8ca8e 3911
f2830aad6e5bf68f 3896
87a844d1066594bf 3894
2f1218a1d2cb579a 3890
68365d5fc0c37016 3888
4c6063b0c8873269 3883
7176190acecfb240 3876
2a5b1722492189eb 3865
2598bc377044267e 3849
15f27fc815c4bda0 3828
84d279bf16b1939f 3827
5190531e8e3db8c8 3822
5c92c462885d62eb 3821
774bf87bc8badf28 3821
c1f2b35ec38d9862 3818
a8bd1d7d7e21026c 3815
5dd2d14aed31ebc0 3815
b1d855a5035b657d 3804
e064bb8d09ccb7be 3799
c471792ec74b4ca1 3793
134785fc54bd4b22 3791
4c65786e1b2872ad 3785
529c6f3f33280fba 3782
30ab26b47b9818d6 3767
6460d4a288ea6fdc 3762
cbdb2fee381e1a26 3761
7b71113be53a03d6 3761
9ad2f9b0e8db5f2a 3761
84f9e07bd9722cb4 3754
fbba6939e4a51862 3754
04c3582bc37740d0 3753
c51ff965ebd43e3a 3750
615e1e7efcefaeee 3750
1457a1d656520084 3749
611b5c9396048284 3748
73f58925b42d5d05 3743
b69b9c47603f0fb6 3743
e8ec2ccfb11077b7 3742"""


def _load_costs() -> dict[str, int]:
    costs: dict[str, int] = {}
    for line in _RECORDED_COST_LINES.splitlines():
        digest_prefix, millis_text = line.split()
        millis = int(millis_text)
        if not _PREFIX.fullmatch(digest_prefix) or digest_prefix in costs or millis <= 0:
            raise ValueError("Invalid or duplicate pinned Python CI cost")
        costs[digest_prefix] = millis
    if len(costs) != 200:
        raise ValueError("Incomplete Python CI cost profile")
    return costs


_COSTS_MS = _load_costs()


def select_shards(
    digests: Sequence[str],
    count: int,
    *,
    costs_ms: Mapping[str, int] | None = None,
) -> tuple[frozenset[str], ...]:
    """Stable longest-predicted-first bin packing; preserve all full SHA-256 IDs."""
    if count < 1 or not digests or len(set(digests)) != len(digests):
        raise ValueError("Invalid or duplicate Python shard collection")
    if any(not _DIGEST.fullmatch(digest) for digest in digests):
        raise ValueError("Invalid Python test digest")
    # Detect even an improbable prefix collision instead of mispricing two tests.
    if len({digest[:16] for digest in digests}) != len(digests):
        raise ValueError("Colliding Python test cost prefixes")

    profile = _COSTS_MS if costs_ms is None else costs_ms

    def cost(digest: str) -> int:
        millis = profile.get(digest[:16], _UNKNOWN_COST_MS)
        if not isinstance(millis, int) or millis <= 0:
            raise ValueError("Invalid Python shard timing cost")
        return millis

    loads = [0] * count
    buckets: list[set[str]] = [set() for _ in range(count)]
    for digest in sorted(digests, key=lambda value: (-cost(value), value)):
        number = min(range(count), key=lambda index: (loads[index], index))
        buckets[number].add(digest)
        loads[number] += cost(digest)
    return tuple(frozenset(bucket) for bucket in buckets)
