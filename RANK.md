# 合批秩一致性复查

榆川计量组保留现有的普通质控报告，并为夜班增加按封存号签发的秩一致性报告。两种报告可以使用同一批封存件。V1 日常工作流、Python 接口和运行方式见 `README.md`。

## 封存与旧库

`freeze.package.seal_batch(db, batch_id)` 首次封存时，同时发布原有普通统计和可供秩签发消费的联合证据。按批绑定的刻度分别换算两轴，只采纳同一行的双非空读数。以精确有理数保全统一坐标的配对和出现次数。相等值按数值解释，例如 `1` 与 `2/2` 相等。原始行仍按原期限清理，清理后秩签发仅消费指定封存件的证据。

一个封存件的证据可以完整且含零对。V1 已存在的封存件属缺证件，仍按原接口领取和计算普通报告。原始行尚可用时重复封存沿用已有的原件领取语义。由新版 `db.initialize(db)` 打开并初始化已有 V1 工作库后，可继续按原号读取既有封存、普通报告和清理回执，也可继续接纳和封存后续批次。普通报告继续使用原统计口径。

## 签发与领取

两个新入口均在 `review.reports` 中。

- `issue_rank_review(db, seal_ids, threshold)` 接受与 `issue_review` 相同的选件参数。编号是正的 SQLite 整数，选件非空、互异、存在且来自同一项目。门槛是 `[-1,1]` 内的有理数，接受整数、`Fraction` 和可解析的数值字符串。布尔值和浮点数无效。任一选件缺证或请求非法时抛出 `ValueError`，整次拒发。
- `get_rank_review(db, report_id)` 按秩报告号读取原签发结果。有效编号在秩报告中查无记录时返回 `None`，编号非法时抛出 `ValueError`。
- 两个入口的成功结果都有 `report_id`、`project`、`seal_ids`、`threshold`、`n`、`q`、`passed` 字段。`seal_ids` 为按号升序的元组，`threshold` 和有定义的 `q` 为 `Fraction`，`n` 是有效对数，`passed` 为布尔值。每次成功签发保存一份报告。读取使用已保存的原门槛、选件和结果。批和刻度更正、清理及关闭重开均保留旧绑定与结果。

在本次所选封存件的全部有效对上，对横轴和纵轴分别按精确坐标升序赋秩，位置从 1 开始。同轴的一组等值占用连续位置，每个出现取这些位置的平均秩。保留同一观测行的横纵秩配对及其重数。在成对秩上使用 README 中的 `A`、`B`、`C` 公式，`q = C*abs(C)/(A*B)`。少于两对或任一轴的秩无离散时，仍签发 `q=None`、`passed=False` 的报告。其余情况以 `q >= threshold` 裁决。允许全量展开配对并排序。

新封存与新报告分别在各自的写入事务内完整发布。SQLite 提交异常向调用方传播，当次写入整体回滚，解除故障后可重试。

## 样例与交付核账

`python3 -B -m rank_examples` 运行 V1 对照。`rank_examples.py` 也提供以下核验所用的原始行和上报辅助函数。

| 输入 | 预期秩报告 |
| --- | --- |
| `MOMENT_A`、`MOMENT_B` 分别封存和清理后，各自以门槛 0 签发 | 两份均 `n=4`。前者 `q=1/10` 且通过，后者 `q=-1/10` 且拒绝。两份普通报告均为 `q=0` 且通过。 |
| `CROSS_LEFT` 用默认刻度，`CROSS_RIGHT` 用台架 `b` 和 `x_slope=-1, x_offset=2` 封存。双件以门槛 `1/2` 签发 | 统一配对为 `(0,0),(1,1),(1,0),(2,1)`。`n=4, q=1/2`，等门槛通过。反序选件也返回升序封存号及同样的统计和裁决。 |
| `REPEATED` 默认刻度，仅选该封存件 | `n=4, q=2/27`。两个 `(0,0)` 都计入，两个单轴缺测行均不入样。 |
| `ZERO_PAIRS` 新封存，清理后单选 | `n=0, q=None, passed=False`。同项目的缺证旧封存即使也是零对，单选或混选均整次拒发。 |

跨批调用示例在新增入口实现后可运行。`db` 为已初始化的工作库。

```python
from freeze.package import seal_batch
from rank_examples import CROSS_LEFT, CROSS_RIGHT, submit_fixture
from review.reports import get_rank_review, issue_rank_review

left = seal_batch(db, submit_fixture(db, 'cross-left', CROSS_LEFT))
right = seal_batch(db, submit_fixture(
    db, 'cross-right', CROSS_RIGHT, bench='b', x_slope=-1, x_offset=2,
))
report = issue_rank_review(db, [right.seal_id, left.seal_id], '1/2')
assert report.n == 4 and report.q == report.threshold and report.passed
assert get_rank_review(db, report.report_id) == report
```

交付时沿 `.pointwise-runtime.json` 接通原测试与新增业务核验，失败以非零退出。核对清理后同矩异秩、换标后的跨批并列、相同配对的重复出现、零对和常量轴。用派生初始版本创建 V1 工作库及其零对封存和普通报告，再用实现后的版本续写，核对缺证拒发、V1 读回及新空件成功签发。沿 `tests/support.py` 的延迟外键夹具做法分别触发封存和秩报告的提交失败，核对回滚并重试。演示入口应展示清理后签发、追加更正并重开后领取原秩报告的实际结果。附一段说明，写清签发如何识别完整证据，以及如何区分缺证件与零对件。
