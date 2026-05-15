<?php
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST, GET, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit();
}

$input = json_decode(file_get_contents('php://input'), true);
if (!is_array($input)) {
    $input = [];
}

/** Cockpit pre-load: same Yahoo OHLCV as /api/history.php (GC=F / MGC=F). */
if (!empty($input['history_only'])) {
    require_once __DIR__ . '/_cem_yahoo_bars.inc.php';
    $sym = isset($input['symbol']) ? $input['symbol'] : 'MGC';
    $yahoo = cem_yahoo_map_symbol($sym);
    $pack = cem_fetch_yahoo_bars($yahoo, '1d', '5y');
    if ($pack === null || empty($pack['bars'])) {
        http_response_code(502);
        echo json_encode(['error' => 'history_fetch_failed', 'symbol' => $sym]);
        exit();
    }
    $bars = $pack['bars'];
    echo json_encode([
        'history_only' => true,
        'symbol' => strtoupper(preg_replace('/[^A-Za-z0-9]/', '', (string) $sym)),
        'yahoo' => $pack['yahoo'],
        'bars' => $bars,
        'ohlcv' => $bars,
        'count' => count($bars),
    ]);
    exit();
}

$strategy = isset($input['strategy']) ? $input['strategy'] : 'default';

// Generate backtest results
$results = [];
for ($i = 0; $i < 100; $i++) {
    $results[] = [
        'time' => $i,
        'price' => round(5000 + sin($i / 12) * 400 + rand(0, 120), 2),
        'equity' => round(10000 + ($i * 65) + rand(0, 150), 2)
    ];
}

$summary = [
    'total_trades' => 42,
    'win_rate' => 0.67,
    'total_return' => 0.18,
    'sharpe_ratio' => 1.4
];

// Save to DB if DATABASE_URL is set
$db_status = 'not configured';
$run_id = null;

$database_url = getenv('DATABASE_URL');
if ($database_url) {
    // Parse postgres URL: postgres://user:pass@host:port/dbname
    $parsed = parse_url($database_url);
    if ($parsed) {
        $host = $parsed['host'];
        $port = isset($parsed['port']) ? $parsed['port'] : 5432;
        $user = $parsed['user'];
        $pass = $parsed['pass'];
        $dbname = ltrim($parsed['path'], '/');

        $conn_str = "host={$host} port={$port} dbname={$dbname} user={$user} password={$pass} sslmode=require";

        if (function_exists('pg_connect')) {
            $conn = @pg_connect($conn_str);
            if ($conn) {
                // Create table if needed
                pg_query($conn, "CREATE TABLE IF NOT EXISTS backtest_runs (
                    id SERIAL PRIMARY KEY,
                    strategy VARCHAR(100),
                    results JSONB,
                    summary JSONB,
                    created_at TIMESTAMP DEFAULT NOW()
                )");

                // Insert run
                $results_json = pg_escape_string($conn, json_encode($results));
                $summary_json = pg_escape_string($conn, json_encode($summary));
                $strategy_esc = pg_escape_string($conn, $strategy);

                $res = pg_query($conn, "INSERT INTO backtest_runs (strategy, results, summary) VALUES ('{$strategy_esc}', '{$results_json}', '{$summary_json}') RETURNING id");
                if ($res) {
                    $row = pg_fetch_assoc($res);
                    $run_id = intval($row['id']);
                    $db_status = 'connected';
                } else {
                    $db_status = 'error: ' . pg_last_error($conn);
                }
                pg_close($conn);
            } else {
                $db_status = 'error: connection failed';
            }
        } else {
            $db_status = 'error: pg_connect not available';
        }
    } else {
        $db_status = 'error: could not parse DATABASE_URL';
    }
}

$response = [
    'status' => 'success',
    'strategy' => $strategy,
    'results' => $results,
    'summary' => $summary,
    'db' => $db_status
];

if ($run_id !== null) {
    $response['run_id'] = $run_id;
}

echo json_encode($response);
