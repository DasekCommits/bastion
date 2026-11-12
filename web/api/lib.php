<?php
declare(strict_types=1);

const ORIGIN = 'https://bastion.dasek.dev';
const TIERS = ['small', 'medium', 'large'];

function private_dir(): string
{
    return dirname(__DIR__, 2) . '/bastion-private';
}

function config(): array
{
    static $config = null;
    if ($config === null) {
        $config = [];
        $lines = @file(private_dir() . '/config.env', FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) ?: [];
        foreach ($lines as $line) {
            $line = trim($line);
            if ($line === '' || $line[0] === '#' || !str_contains($line, '=')) {
                continue;
            }
            [$key, $value] = explode('=', $line, 2);
            $config[trim($key)] = trim($value);
        }
    }
    return $config;
}

function db(): PDO
{
    static $pdo = null;
    if ($pdo === null) {
        $c = config();
        $pdo = new PDO(
            sprintf('mysql:host=%s;dbname=%s;charset=utf8mb4', $c['DB_HOST'] ?? 'localhost', $c['DB_NAME'] ?? ''),
            $c['DB_USER'] ?? '',
            $c['DB_PASS'] ?? '',
            [
                PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
                PDO::ATTR_EMULATE_PREPARES => false,
            ]
        );
    }
    return $pdo;
}

function start_session(): void
{
    $dir = private_dir() . '/sessions';
    if (!is_dir($dir)) {
        mkdir($dir, 0700, true);
    }
    session_save_path($dir);
    ini_set('session.use_strict_mode', '1');
    ini_set('session.gc_maxlifetime', (string) (60 * 60 * 24 * 30));
    session_name('bastion_session');
    session_set_cookie_params([
        'lifetime' => 60 * 60 * 24 * 30,
        'path' => '/',
        'secure' => true,
        'httponly' => true,
        'samesite' => 'Lax',
    ]);
    session_start();
}

function send_json(array $data, int $status = 200): never
{
    http_response_code($status);
    header('Content-Type: application/json');
    header('Cache-Control: no-store, private');
    header('X-Accel-Expires: 0');
    header('Set-Cookie: _mcnc=1; Max-Age=31536000; Path=/; Secure; SameSite=Lax', false);
    header('X-Content-Type-Options: nosniff');
    echo json_encode($data);
    exit;
}

function require_post(): void
{
    if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
        send_json(['error' => 'Use POST.'], 405);
    }
    if (($_SERVER['HTTP_ORIGIN'] ?? '') !== ORIGIN || ($_SERVER['HTTP_X_BASTION'] ?? '') !== '1') {
        send_json(['error' => 'This request did not come from the Bastion page.'], 403);
    }
}

function current_user(): ?array
{
    $id = $_SESSION['user_id'] ?? null;
    if (!is_int($id)) {
        return null;
    }
    $stmt = db()->prepare('SELECT id, login, avatar_url, points, games, wins, secrets, learned, achievements, owned, gifted, migrated, realism_red, realism_blue, realism_red_secs, realism_blue_secs FROM users WHERE id = ?');
    $stmt->execute([$id]);
    return $stmt->fetch() ?: null;
}

function github_request(string $url, array $options): array
{
    $handle = curl_init($url);
    curl_setopt_array($handle, $options + [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 10,
        CURLOPT_USERAGENT => 'Bastion',
    ]);
    $body = curl_exec($handle);
    $status = curl_getinfo($handle, CURLINFO_HTTP_CODE);
    curl_close($handle);
    $data = is_string($body) ? json_decode($body, true) : null;
    if ($status !== 200 || !is_array($data)) {
        throw new RuntimeException('GitHub did not answer as expected.');
    }
    return $data;
}
