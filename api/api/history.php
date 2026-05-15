<?php
/**
 * Daily (and other) OHLCV proxy for cockpit pre-load — Yahoo Finance chart API.
 * GET ?symbol=MGC&interval=1d&range=5y
 */
require_once __DIR__ . '/_cem_yahoo_bars.inc.php';

header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
header('Content-Type: application/json; charset=utf-8');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit();
}

if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    http_response_code(405);
    echo json_encode(['error' => 'method_not_allowed']);
    exit();
}

$symbol = isset($_GET['symbol']) ? strtoupper(preg_replace('/[^A-Za-z0-9=.\-\/]/', '', $_GET['symbol'])) : 'MGC';
$interval = isset($_GET['interval']) ? preg_replace('/[^0-9a-z]/i', '', $_GET['interval']) : '1d';
$range = isset($_GET['range']) ? preg_replace('/[^0-9a-z]/i', '', $_GET['range']) : '5y';

$allowedRanges = ['1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'max'];
if (!in_array($range, $allowedRanges, true)) {
    $range = '5y';
}
$allowedInt = ['1d', '1wk', '1mo'];
if (!in_array($interval, $allowedInt, true)) {
    $interval = '1d';
}

$yahoo = cem_yahoo_map_symbol($symbol);
$pack = cem_fetch_yahoo_bars($yahoo, $interval, $range);

if ($pack === null) {
    http_response_code(502);
    echo json_encode(['error' => 'upstream_fetch_failed', 'symbol' => $symbol]);
    exit();
}

$bars = $pack['bars'];
if (count($bars) === 0) {
    http_response_code(404);
    echo json_encode(['error' => 'no_valid_bars', 'symbol' => $symbol, 'yahoo' => $pack['yahoo']]);
    exit();
}

echo json_encode([
    'symbol' => $symbol,
    'yahoo' => $pack['yahoo'],
    'interval' => $interval,
    'range' => $range,
    'bars' => $bars,
    'count' => count($bars),
]);
