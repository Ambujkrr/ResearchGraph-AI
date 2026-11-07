# Phase 4.5 repeated exploratory evaluation

Five overlapping random edge splits; intervals are descriptive t-based summaries, not independent prospective confidence intervals. Sampled AUC/AP use a balanced positive/unlabeled set; ranking uses the full eligible local target pool. Hyperparameters were selected separately for each seed using validation loss only.

## Full corpus

| Method | Metric | Mean | SD | Descriptive 95% interval |
|---|---|---:|---:|---:|
| graphsage | roc_auc | 0.7955 | 0.0536 | [0.7290, 0.8621] |
| graphsage | average_precision | 0.7659 | 0.0618 | [0.6891, 0.8427] |
| graphsage | precision_at_k | 0.0345 | 0.0111 | [0.0207, 0.0483] |
| graphsage | recall_at_k | 0.2515 | 0.0782 | [0.1544, 0.3485] |
| graphsage | hits_at_k | 0.2937 | 0.0952 | [0.1755, 0.4119] |
| graphsage | mrr | 0.1448 | 0.0638 | [0.0656, 0.2241] |
| cosine | roc_auc | 0.6769 | 0.0155 | [0.6577, 0.6961] |
| cosine | average_precision | 0.6860 | 0.0180 | [0.6636, 0.7084] |
| cosine | precision_at_k | 0.0462 | 0.0014 | [0.0445, 0.0479] |
| cosine | recall_at_k | 0.3300 | 0.0239 | [0.3003, 0.3597] |
| cosine | hits_at_k | 0.3958 | 0.0206 | [0.3702, 0.4213] |
| cosine | mrr | 0.2067 | 0.0285 | [0.1714, 0.2421] |
| popularity | roc_auc | 0.8573 | 0.0253 | [0.8259, 0.8886] |
| popularity | average_precision | 0.8357 | 0.0339 | [0.7936, 0.8778] |
| popularity | precision_at_k | 0.0591 | 0.0092 | [0.0477, 0.0706] |
| popularity | recall_at_k | 0.4412 | 0.0534 | [0.3749, 0.5076] |
| popularity | hits_at_k | 0.5062 | 0.0637 | [0.4271, 0.5852] |
| popularity | mrr | 0.2329 | 0.0301 | [0.1955, 0.2703] |
| common_neighbors | roc_auc | 0.7158 | 0.0203 | [0.6905, 0.7410] |
| common_neighbors | average_precision | 0.7047 | 0.0211 | [0.6784, 0.7309] |
| common_neighbors | precision_at_k | 0.0511 | 0.0043 | [0.0459, 0.0564] |
| common_neighbors | recall_at_k | 0.3629 | 0.0108 | [0.3494, 0.3764] |
| common_neighbors | hits_at_k | 0.4385 | 0.0205 | [0.4131, 0.4639] |
| common_neighbors | mrr | 0.2203 | 0.0203 | [0.1951, 0.2456] |
| adamic_adar | roc_auc | 0.7181 | 0.0209 | [0.6921, 0.7440] |
| adamic_adar | average_precision | 0.7184 | 0.0231 | [0.6898, 0.7471] |
| adamic_adar | precision_at_k | 0.0529 | 0.0070 | [0.0442, 0.0617] |
| adamic_adar | recall_at_k | 0.3779 | 0.0318 | [0.3384, 0.4173] |
| adamic_adar | hits_at_k | 0.4466 | 0.0479 | [0.3871, 0.5061] |
| adamic_adar | mrr | 0.2349 | 0.0182 | [0.2123, 0.2575] |

| Seed | Experiment | Nodes | Best epoch | Epochs run | Validation loss | GNN AUC | GNN AP | Popularity AUC |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 101 | 3 | 502 | 19 | 25 | 0.5644 | 0.8231 | 0.7676 | 0.8954 |
| 202 | 5 | 502 | 15 | 21 | 0.5809 | 0.7556 | 0.7323 | 0.8290 |
| 303 | 7 | 502 | 21 | 27 | 0.5207 | 0.8543 | 0.8299 | 0.8450 |
| 404 | 9 | 502 | 34 | 40 | 0.4910 | 0.8202 | 0.8190 | 0.8500 |
| 505 | 11 | 502 | 22 | 28 | 0.5905 | 0.7244 | 0.6807 | 0.8670 |

## Four title-rule exclusions

| Method | Metric | Mean | SD | Descriptive 95% interval |
|---|---|---:|---:|---:|
| graphsage | roc_auc | 0.7705 | 0.0315 | [0.7313, 0.8096] |
| graphsage | average_precision | 0.7373 | 0.0286 | [0.7018, 0.7728] |
| graphsage | precision_at_k | 0.0244 | 0.0078 | [0.0147, 0.0342] |
| graphsage | recall_at_k | 0.1850 | 0.0504 | [0.1225, 0.2475] |
| graphsage | hits_at_k | 0.2192 | 0.0696 | [0.1328, 0.3056] |
| graphsage | mrr | 0.0896 | 0.0359 | [0.0450, 0.1342] |
| cosine | roc_auc | 0.7039 | 0.0300 | [0.6667, 0.7412] |
| cosine | average_precision | 0.7030 | 0.0325 | [0.6627, 0.7433] |
| cosine | precision_at_k | 0.0458 | 0.0021 | [0.0433, 0.0484] |
| cosine | recall_at_k | 0.3443 | 0.0171 | [0.3231, 0.3656] |
| cosine | hits_at_k | 0.4050 | 0.0149 | [0.3865, 0.4235] |
| cosine | mrr | 0.2129 | 0.0219 | [0.1858, 0.2401] |
| popularity | roc_auc | 0.8457 | 0.0208 | [0.8200, 0.8715] |
| popularity | average_precision | 0.8354 | 0.0303 | [0.7978, 0.8730] |
| popularity | precision_at_k | 0.0601 | 0.0066 | [0.0520, 0.0683] |
| popularity | recall_at_k | 0.4281 | 0.0500 | [0.3660, 0.4901] |
| popularity | hits_at_k | 0.5034 | 0.0577 | [0.4317, 0.5751] |
| popularity | mrr | 0.2369 | 0.0218 | [0.2099, 0.2640] |
| common_neighbors | roc_auc | 0.7153 | 0.0209 | [0.6893, 0.7413] |
| common_neighbors | average_precision | 0.7029 | 0.0242 | [0.6729, 0.7330] |
| common_neighbors | precision_at_k | 0.0542 | 0.0063 | [0.0463, 0.0620] |
| common_neighbors | recall_at_k | 0.3871 | 0.0267 | [0.3540, 0.4203] |
| common_neighbors | hits_at_k | 0.4674 | 0.0524 | [0.4024, 0.5325] |
| common_neighbors | mrr | 0.2581 | 0.0460 | [0.2009, 0.3152] |
| adamic_adar | roc_auc | 0.7176 | 0.0209 | [0.6916, 0.7436] |
| adamic_adar | average_precision | 0.7158 | 0.0252 | [0.6845, 0.7471] |
| adamic_adar | precision_at_k | 0.0559 | 0.0067 | [0.0476, 0.0643] |
| adamic_adar | recall_at_k | 0.4000 | 0.0340 | [0.3578, 0.4423] |
| adamic_adar | hits_at_k | 0.4833 | 0.0535 | [0.4168, 0.5497] |
| adamic_adar | mrr | 0.2538 | 0.0427 | [0.2008, 0.3067] |

| Seed | Experiment | Nodes | Best epoch | Epochs run | Validation loss | GNN AUC | GNN AP | Popularity AUC |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 101 | 4 | 498 | 8 | 14 | 0.5919 | 0.7433 | 0.6993 | 0.8486 |
| 202 | 6 | 498 | 14 | 20 | 0.5560 | 0.7616 | 0.7546 | 0.8235 |
| 303 | 8 | 498 | 9 | 15 | 0.6052 | 0.7579 | 0.7238 | 0.8318 |
| 404 | 10 | 498 | 16 | 22 | 0.5564 | 0.8249 | 0.7739 | 0.8778 |
| 505 | 12 | 498 | 18 | 24 | 0.6494 | 0.7647 | 0.7350 | 0.8470 |

