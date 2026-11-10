<?php
declare(strict_types=1);

if (PHP_SAPI !== 'cli') {
    exit(1);
}

$web = $argv[1] ?? '';
require $web . '/api/lib.php';

db()->exec(
    'CREATE TABLE IF NOT EXISTS users (
        id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        github_id BIGINT UNSIGNED NOT NULL UNIQUE,
        login VARCHAR(64) NOT NULL,
        avatar_url VARCHAR(255) NOT NULL DEFAULT \'\',
        points INT UNSIGNED NOT NULL DEFAULT 0,
        games INT UNSIGNED NOT NULL DEFAULT 0,
        wins TEXT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_login DATETIME NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'
);

echo "Tables ready.\n";
