<?php
/**
 * Shared Yahoo Finance v8 chart → OHLCV bars (used by history.php and backtest.php history_only).
 *
 * @return array<int, array{t:int,o:float,h:float,l:float,c:float,v:int}>|null
 */
function cem_yahoo_map_symbol($symbol)
{
    $symbol = strtoupper(preg_replace('/[^A-Za-z0-9=.\-\/]/', '', $symbol));
    $yahooMap = [
        'MGC' => 'MGC=F',
        'MES' => 'MES=F',
        'MNQ' => 'MNQ=F',
        'MYM' => 'MYM=F',
        'M2K' => 'M2K=F',
        'MCL' => 'MCL=F',
        'GC' => 'GC=F',
        'ES' => 'ES=F',
        'NQ' => 'NQ=F',
        'CL' => 'CL=F',
        'BTC' => 'BTC-USD',
        'ETH' => 'ETH-USD',
        'SOL' => 'SOL-USD',
        'SPY' => 'SPY',
        'QQQ' => 'QQQ',
    ];
    $yahoo = isset($yahooMap[$symbol]) ? $yahooMap[$symbol] : $symbol;
    if (strpos($yahoo, '=') === false && strpos($yahoo, '-') === false && strlen($symbol) <= 4 && preg_match('/^[A-Z]+$/', $symbol)) {
        $yahoo = $symbol . '=F';
    }
    return $yahoo;
}

/** @return array|null [ 'bars' => [...], 'yahoo' => string ] or null */
function cem_fetch_yahoo_bars($yahoo, $interval, $range)
{
    $url = 'https://query1.finance.yahoo.com/v8/finance/chart/' . rawurlencode($yahoo)
        . '?interval=' . rawurlencode($interval)
        . '&range=' . rawurlencode($range);

    $ctx = stream_context_create([
        'http' => [
            'header' => "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36\r\nAccept: application/json\r\n",
            'timeout' => 15,
            'ignore_errors' => true,
        ],
        'ssl' => [
            'verify_peer' => true,
            'verify_peer_name' => true,
        ],
    ]);

    $raw = @file_get_contents($url, false, $ctx);
    if ($raw === false) {
        return null;
    }

    $j = json_decode($raw, true);
    if (!$j || !isset($j['chart']['result'][0])) {
        return null;
    }

    $res = $j['chart']['result'][0];
    $ts = isset($res['timestamp']) ? $res['timestamp'] : [];
    $q = isset($res['indicators']['quote'][0]) ? $res['indicators']['quote'][0] : [];
    $open = isset($q['open']) ? $q['open'] : [];
    $high = isset($q['high']) ? $q['high'] : [];
    $low = isset($q['low']) ? $q['low'] : [];
    $close = isset($q['close']) ? $q['close'] : [];
    $vol = isset($q['volume']) ? $q['volume'] : [];

    $bars = [];
    $n = count($ts);
    for ($i = 0; $i < $n; $i++) {
        $o = isset($open[$i]) ? $open[$i] : null;
        $h = isset($high[$i]) ? $high[$i] : null;
        $l = isset($low[$i]) ? $low[$i] : null;
        $c = isset($close[$i]) ? $close[$i] : null;
        if ($o === null || $h === null || $l === null || $c === null) {
            continue;
        }
        if (!is_numeric($o) || !is_numeric($h) || !is_numeric($l) || !is_numeric($c)) {
            continue;
        }
        $v = isset($vol[$i]) && is_numeric($vol[$i]) ? (int) $vol[$i] : 0;
        $bars[] = [
            't' => (int) $ts[$i],
            'o' => round((float) $o, 6),
            'h' => round((float) $h, 6),
            'l' => round((float) $l, 6),
            'c' => round((float) $c, 6),
            'v' => $v,
        ];
    }

    return ['bars' => $bars, 'yahoo' => $yahoo];
}
