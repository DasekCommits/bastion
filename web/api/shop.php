<?php
declare(strict_types=1);

require __DIR__ . '/lib.php';

start_session();
$user = current_user();
if ($user === null) {
    send_json(['error' => 'Sign in to earn coins and buy from the shop.'], 401);
}
$catalog = (require __DIR__ . '/shop_data.php') ?: ['items' => [], 'per_coin' => 10];
$pdo = db();

function wallet(PDO $pdo, array $user, array $catalog): array
{
    // coins come only from scores the referee has not rejected, so they cannot be typed in
    $stmt = $pdo->prepare("SELECT side, SUM(points) AS total FROM games
                           WHERE user_id = ? AND points IS NOT NULL AND (verified IS NULL OR verified = 1) GROUP BY side");
    $stmt->execute([$user['id']]);
    $earned = ['red' => 0, 'blue' => 0];
    foreach ($stmt->fetchAll() as $row) {
        if (isset($earned[$row['side']])) {
            $earned[$row['side']] = intdiv((int) $row['total'], (int) $catalog['per_coin']);
        }
    }
    $owned = json_decode((string) ($user['owned'] ?? ''), true) ?: [];
    $gifted = json_decode((string) ($user['gifted'] ?? ''), true) ?: [];
    $spent = ['red' => 0, 'blue' => 0];
    foreach ($owned as $id) {
        $item = $catalog['items'][$id] ?? null;
        if ($item && !in_array($id, $gifted, true)) {
            $spent[$item['side']] += (int) $item['price'];
        }
    }
    return [
        'coins' => ['red' => $earned['red'] - $spent['red'], 'blue' => $earned['blue'] - $spent['blue']],
        'earned' => $earned,
        'owned' => array_values($owned),
    ];
}

if (($_SERVER['REQUEST_METHOD'] ?? '') === 'GET') {
    send_json(wallet($pdo, $user, $catalog));
}

require_post();
$body = json_decode((string) file_get_contents('php://input', false, null, 0, 2048), true);
$id = (string) ($body['item'] ?? '');
$item = $catalog['items'][$id] ?? null;
if ($item === null || $item['free']) {
    send_json(['error' => 'That is not for sale.'], 422);
}

$pdo->beginTransaction();
$lock = $pdo->prepare('SELECT owned, gifted FROM users WHERE id = ? FOR UPDATE');
$lock->execute([$user['id']]);
$row = $lock->fetch();
$user['owned'] = $row['owned'];
$user['gifted'] = $row['gifted'];
$wallet = wallet($pdo, $user, $catalog);
if (in_array($id, $wallet['owned'], true)) {
    $pdo->rollBack();
    send_json(['error' => 'You already own it.'] + $wallet, 409);
}
if ($wallet['coins'][$item['side']] < (int) $item['price']) {
    $pdo->rollBack();
    send_json(['error' => 'Not enough coins yet.'] + $wallet, 409);
}
$owned = array_values(array_merge($wallet['owned'], [$id]));
$pdo->prepare('UPDATE users SET owned = ? WHERE id = ?')->execute([json_encode($owned), $user['id']]);
$pdo->commit();
$user['owned'] = json_encode($owned);
send_json(['ok' => true, 'bought' => $id] + wallet($pdo, $user, $catalog));
