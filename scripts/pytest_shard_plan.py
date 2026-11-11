"""Pinned cost-balanced, complete pytest shard planning for required CI.

The 200 highest-median-cost nodeid hashes were measured on the identical
PR HEAD 4f5bcce0f60b96fa557e522fa1bcecac9e7c92ba in successful
GitHub Actions runs 42876864345, 42894370846 and 42903842261.
Each number is the median milliseconds of setup + call + teardown.
Unseen tests use a 2300 ms estimate, never disappear from a shard.
The timings estimate workload, not runner/CI wall time or an achieved SLO.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_PREFIX = re.compile(r"[0-9a-f]{16}\Z")
_UNKNOWN_COST_MS = 2300
_RECORDED_COST_LINES = """1efec5b508d3bd9a 20758
c4e8e1cf35e6b70f 15545
190814867c84cbdb 12428
d42f9a9acf95f864 12230
a52566dfa490ce25 11019
9910016b5e3736bc 10442
7c4f5578706dafc5 10129
02e261e5d7b9f330 9421
2462968bd87b14be 9313
e1ce93bac8c04ee0 9019
99c283631d5a0e9b 8869
401cada1f6cbbc22 8698
f8a6fe2e97d63d36 8675
131e88d7a23ed7e8 8631
cc8da4ed2e374b3e 8606
ce024b99bb2397da 8558
1ce80f6ee2c2edcf 8345
c2786a153f04bb3c 8292
3f74456c5b137c87 8054
3da8b6a5e4de6e25 7863
e771b3e6b8bd2d02 7825
58782dafdf8a20e3 7710
82c29425d1a6ce83 7694
373476f384968806 7476
e42b400ee73fc7b6 7292
ab4f8d21128c2f1b 7204
3bbddcf6db65f281 7045
00643803b6c6ecbc 7014
889b548fc671487e 7008
0c7648d393cee5f4 6977
0b923826ef73cb9e 6963
307ef8df182ff113 6926
9e76ba6f085cc35b 6759
336be0a213453a0c 6703
241166616ef027f0 6642
1db41358681dd360 6513
a8f4d4bea854985f 6482
42d5acf79e06d872 6430
72318d4ba66c193a 6422
a8765c0e014b696b 6400
7a58ff5ae7a852f6 6372
a3555f92fdd119f5 6317
f02cc03d54f167a4 6253
973ecd3e4ffa0e9f 6251
ccfc684b3cc54061 6243
37e40bdbfab12434 6238
e4a4bc0638f97b5e 6215
55667c0b301cce5c 6194
bee3b8d15300e936 6141
586e006868fc44d8 6102
ee906119478b135c 6040
8df419f1efb381d2 6016
dbc9f2b186da5906 6016
fb2e2b1f4d546790 5999
aba1c193019a4860 5938
b8a578e6488ac93a 5774
91aebe7b021180e9 5706
193b599b49c1ceaf 5699
f2946c0008c8d871 5665
6a24dcc488826c50 5565
943c736ef5af29e3 5495
7673f2318e6a1afb 5427
c66e912ce1df175b 5412
dd3a604bb21d48d6 5366
b7976bcbf7e88e28 5310
63441502432c7c67 5273
4dc995dc7350d26e 5214
179e82142b5ce1aa 5204
fb2a5409eaac27ec 5179
2a255eff3ca48eb6 5173
b6a7193988d51de5 5134
b399e58a7b597e2b 5054
22f15b0414193cea 5045
b6f21ff288774672 5042
dd848cb3848b647c 5036
d2dde37efd72bb3e 5027
30ab26b47b9818d6 4989
c497cfb8a7ddb04f 4978
f36050ee6c9758e5 4970
57bc0c138be4cc84 4967
6d67c51712d45532 4918
9b8217ac150a39ff 4907
1065ba33adcaab48 4871
72039af88b1af4a1 4859
86ec4e83b050dd67 4859
fee61f6fa5d0e6af 4856
b977027754be515f 4844
0d41d03c2dffce48 4818
09e922621deb6e29 4816
cb963878c1977e98 4807
5f75a89f57898d18 4799
fe01d73188879bf0 4795
08cb95286c258ece 4779
5c84fee3ac105b49 4771
f9f582d22acdfb28 4763
dc2a264265604a57 4761
2fff6bb6871e044b 4740
a328a2ca248aa0b7 4730
91250d0f8757db31 4719
d3153377b7cdb745 4714
e064bb8d09ccb7be 4698
04caccd921e567cd 4689
154b82467d089ebc 4669
4c65786e1b2872ad 4662
ecd8e5cc6bbdeea2 4640
4d8704f15f1df86a 4631
e5b04b6a148cd1fa 4614
84d279bf16b1939f 4601
f80573b87848207e 4586
b4f3b055785da970 4565
95c553b7f7d05f62 4545
d0e0bf535342f273 4538
0e3e1df97621b718 4503
deb2f94ec082b963 4486
3ac6a686abd7b39c 4485
7960907dc54c958b 4481
a0df18b1e2778245 4470
d8015077565755a8 4450
c8216f177fe7364e 4429
cbdb2fee381e1a26 4410
dbcacda5c76e9532 4297
44201eed610dc226 4284
1e7c6852ce56a041 4268
c63872e3e3cddc5c 4266
52bb0d9f4817507d 4265
65414d7e1bbdaaad 4252
e72e0648a5e109ec 4251
c0730cfd68a5f1c0 4250
19dd5c76aa310e76 4240
540b9d89e2f4c75c 4219
f8f6795c0e3109ad 4200
d9fc5ff52207ea56 4199
f0507850fc133792 4195
fb4107bea5425b37 4191
b8dccd93c8fabc19 4188
ace5ff2beae82073 4158
735d8cff38f91341 4157
5bc9f4a6cc59c502 4154
80f5c14a16e6e5e6 4150
0a85c7e862a217ce 4148
e061f60d05c2cc4b 4134
c51ff965ebd43e3a 4132
578a009d71334f35 4126
530a97d8a14c707f 4094
10d7712d05514adf 4090
1d1f8debec432041 4087
171dbc5fcd3b8c9b 4085
92772d31efa8487c 4079
a443ee8a7ba6fce8 4067
ea46c97501152462 4052
ece52af239bfec51 4040
84f9100e99b647a7 4027
04c3582bc37740d0 4017
39fc1f1d07969cf5 4017
0031a081ddf76f28 3997
613fd96815d72a1b 3983
062e8591229b45bc 3979
02d6ade2321f75b9 3957
1acf623393c4ac90 3950
190e5440ac38a937 3947
024a372cc1aff95e 3944
55ab026a66afad4b 3942
8b77f497d974b167 3940
aa02ff79d570fb88 3937
a62991b8c6177c71 3931
84579a5e57652ec2 3920
20c320feace8ca8e 3912
9d91d8e663cdf7d5 3912
ab482e779f45d4f2 3901
4b486114d8646d45 3898
863c6281f4dd8fa8 3889
42d84cbc9c1bf58b 3874
956827d3216526a2 3873
64f89e48fbfa6d80 3868
15b4a34596fa33af 3862
660171d017a90ffa 3862
d81b2d580e08921c 3854
99abcf00acfb8dd8 3846
b7f7175726e8e996 3840
e3f1b8c40a0d07f0 3828
7a58d4c11ed85d46 3826
95a994555efaa5dc 3813
8a97ab466c7af89f 3812
5f39ff6a47eb552d 3806
c471792ec74b4ca1 3804
9aeaaf4a853ed93a 3796
86fd2a872f69b7a7 3793
5f3113e45b388f9e 3783
2f1218a1d2cb579a 3776
2aaef61d32015f4b 3773
186aa4b7ce9bb52f 3767
c73c7ca7fd05fcc7 3764
cbd09bc2012e9e5d 3759
660089e777b6e222 3754
9ed14ad4402821d4 3752
90564af1de639956 3749
fa6da9771c175731 3746
1ea07e26b6c2df0e 3742
34b4b7b47b490acc 3737
c18037f227c5f572 3735"""


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
