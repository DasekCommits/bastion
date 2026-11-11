<?php
declare(strict_types=1);

require __DIR__ . '/lib.php';

// Read by dasek.dev (same site, different subdomain) to show a visitor's Bastion achievements.
$origin = $_SERVER['HTTP_ORIGIN'] ?? '';
if (in_array($origin, ['https://www.dasek.dev', 'https://dasek.dev', ORIGIN], true)) {
    header('Access-Control-Allow-Origin: ' . $origin);
    header('Access-Control-Allow-Credentials: true');
    header('Vary: Origin');
}
if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'GET') {
    send_json(['error' => 'Use GET.'], 405);
}

$catalog = (require __DIR__ . '/achievements_data.php') ?: ['items' => [], 'goals' => []];
start_session();
try {
    $user = current_user();
} catch (Throwable $error) {
    send_json(['error' => 'Accounts are not available right now.'], 503);
}

$earned = $user ? (json_decode((string) ($user['achievements'] ?? ''), true) ?: []) : [];
$secrets = $user ? (json_decode((string) ($user['secrets'] ?? ''), true) ?: []) : [];
$realism = ($secrets['sealed'] ?? 0) >= ($catalog['goals']['sealed'] ?? 10);
$open = [
    '' => true,
    'realism' => $realism,
    'cleared' => $realism && ($secrets['script'] ?? 0) >= ($catalog['goals']['script'] ?? 3),
];

$items = [];
foreach ($catalog['items'] as $item) {
    $done = in_array($item['id'], $earned, true);
    if ($done || $open[(string) ($item['secret'] ?? '')]) {
        $items[] = ['name' => $item['name'], 'text' => $item['text'], 'done' => $done, 'classified' => false];
    } else {
        $items[] = ['name' => '█████████', 'text' => 'Classified', 'done' => false, 'classified' => true];
    }
}

send_json([
    'signed_in' => $user !== null,
    'login' => $user['login'] ?? null,
    'earned' => count(array_filter($items, fn ($i) => $i['done'])),
    'items' => $items,
]);
