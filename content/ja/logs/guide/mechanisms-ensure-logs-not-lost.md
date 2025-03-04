---
aliases:
- /ja/logs/faq/log-collection-is-the-datadog-agent-losing-logs
further_reading:
- link: /logs/log_collection/
  tag: Documentation
  text: ログの収集方法
- link: /logs/explorer/
  tag: Documentation
  text: ログの調査方法
- link: /glossary/#tail
  tag: 用語集
  text: 用語集 "テール" の項目
title: ログの紛失を防ぐメカニズム
---

**Datadog Agent には、ログが失われないようにするためのメカニズムがいくつかあります**。

## ログのローテーション

ファイルがローテーションされると、Agent は古いファイルの[テール][1]を継続しながら、新しく作成されたファイルのテールを並行して開始します。
Agent は古いファイルをテールし続けますが、Agent が最新のファイルをテールするためにリソースを使用していることを確認するために、ログローテーション後に 60 秒のタイムアウトが設定されます。

## ネットワークの問題

### ファイルテール

Agent は、各テールファイルのポインタを保存します。ネットワーク接続に問題がある場合、Agent は接続が回復するまでログの送信を停止し、ログが失われないように停止した場所を自動的にピックアップします。

### ポートリスニング

Agent が TCP または UDP ポートをリッスンしていてネットワークの問題に直面した場合、ネットワークが再び利用可能になるまで、ログはローカルバッファに保存されます。
ただし、メモリの問題を避けるために、このバッファにはいくつかの制限があります。バッファがいっぱいになると、新しいログは削除されます。

### コンテナログ

ファイルに関しては、Datadog はテールされたコンテナ毎にポインタを保存します。そのため、ネットワークに問題が発生した場合、Agent はどのログがまだ送信されていないかを知ることができます。
ただし、ネットワークが再び利用可能になる前にテールコンテナが削除されると、ログにはアクセスできなくなります。

{{< partial name="whats-next/whats-next.html" >}}

[1]: /ja/glossary/#tail