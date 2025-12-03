# Todo List

## 交易量分析 (Volume Analysis)
- [x] 在表格中展示交易量数据
    - volume24h
    - volume7d
    - volume30d
- [x] 在表格中展示交易量变化百分比
    - volumePercentChange24
    - volumePercentChange7d
    - volumePercentChange30d

同时监控变化百分比，如果超过阈值如10%，则推送到webhook

- 通过交易量（当天的交易量）排序，来控制legend的显示顺序
- 不要使用等差的间隔，而是使用等比的间隔（避免小额交易量代币集中在底部）
- 