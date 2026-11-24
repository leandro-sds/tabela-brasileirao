<?php
declare(strict_types=1);

// ============================================================
// update_tabela.php
//
// Lê a tabela do Brasileirão Série A e B no Terra e grava
// cache_tabela_A.json e cache_tabela_B.json no diretório público,
// de onde o complemento do NVDA faz a leitura rápida.
//
// Deve ser executado via CLI (cron), nunca pela web.
//
// Hospedagem: cPanel, PHP 8.3, site www.leandross.com.br
// ============================================================

if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit;
}

// ============================================================
// CONFIGURAÇÃO — só estas quatro linhas precisam de atenção
// ============================================================

// Diretório privado (log e lock). Fica FORA da pasta pública do site.
$PRIVATE_DIR = '/home2/SEU_USUARIO/privado';

// Diretório público, servido em https://www.leandross.com.br/tabela/
$PUBLIC_DIR  = '/home2/SEU_USUARIO/leandross.com.br/tabela';

// Intervalo mínimo entre atualizações de cada série, em segundos.
// 1800 = 30 min. Para a tabela ficar mais fresca, baixe este valor
// e aumente a frequência do cron na mesma proporção (ver README).
$MIN_INTERVAL_SECONDS = 1800;

// Quando a página do Terra não traz a tabela (fim de temporada, fase de
// playoff), não há o que buscar. Nesse caso esperamos este tempo antes de
// tentar de novo, para não encher o log com a mesma mensagem.
$SEM_TABELA_COOLDOWN = 21600; // 6 horas

// ============================================================
// Daqui para baixo não precisa mexer.
// ============================================================

$LOG_PATH  = $PRIVATE_DIR . '/update_tabela.log';
$LOCK_PATH = $PRIVATE_DIR . '/update_tabela.lock';

$SOURCES = [
    'A' => [
        'url'  => 'https://www.terra.com.br/esportes/futebol/brasileiro-serie-a/tabela/',
        'file' => $PUBLIC_DIR . '/cache_tabela_A.json',
    ],
    'B' => [
        'url'  => 'https://www.terra.com.br/esportes/futebol/brasileiro-serie-b/tabela/',
        'file' => $PUBLIC_DIR . '/cache_tabela_B.json',
    ],
];

// Menos linhas que isto e consideramos que a página não tem a tabela.
const MIN_TIMES = 16;

/** A página respondeu, mas não traz tabela de classificação. */
class SemTabelaException extends RuntimeException {}

function logLine(string $path, string $msg): void
{
    @file_put_contents($path, '[' . date('c') . '] ' . $msg . PHP_EOL, FILE_APPEND);
}

function fetchUrl(string $url): string
{
    $ch = curl_init($url);
    if ($ch === false) {
        throw new RuntimeException("Falha ao iniciar cURL");
    }

    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_FOLLOWLOCATION => true,
        CURLOPT_MAXREDIRS      => 5,
        CURLOPT_CONNECTTIMEOUT => 15,
        CURLOPT_TIMEOUT        => 30,
        CURLOPT_ENCODING       => '',
        CURLOPT_USERAGENT      => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                . 'AppleWebKit/537.36 (KHTML, like Gecko) '
                                . 'Chrome/124.0 Safari/537.36',
        CURLOPT_HTTPHEADER     => [
            'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language: pt-BR,pt;q=0.9,en;q=0.8',
        ],
    ]);

    $html = curl_exec($ch);
    if ($html === false) {
        $err = curl_error($ch);
        curl_close($ch);
        throw new RuntimeException("Erro ao baixar HTML: {$err}");
    }

    $status = (int) curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
    curl_close($ch);

    if ($status < 200 || $status >= 300) {
        throw new RuntimeException("HTTP {$status} ao acessar {$url}");
    }

    return $html;
}

function normalizeTeamName(string $name): string
{
    $name = trim($name);
    $name = preg_replace('/\s*>>\s*$/u', '', $name) ?? $name;
    return trim($name);
}

function teamSigla(string $teamName): ?string
{
    $map = [
        'Palmeiras'=>'PAL','São Paulo'=>'SAO','Corinthians'=>'COR','Bahia'=>'BAH',
        'Fluminense'=>'FLU','Athletico-PR'=>'CAP','Bragantino'=>'BGT','Grêmio'=>'GRE',
        'Chapecoense'=>'CHA','Mirassol'=>'MIR','Flamengo'=>'FLA','Coritiba'=>'CFC',
        'Santos'=>'SAN','Botafogo'=>'BOT','Vitória'=>'VIT','Remo'=>'REM',
        'Atlético-MG'=>'CAM','Internacional'=>'INT','Cruzeiro'=>'CRU',
        'Vasco da Gama'=>'VAS','Vasco'=>'VAS','Ceará'=>'CEA','Fortaleza'=>'FOR',
        'Juventude'=>'JUV','Sport'=>'SPT','Novorizontino'=>'NOV','Goiás'=>'GOI',
        'Atlético-GO'=>'ACG','Vila Nova'=>'VIL','Criciúma'=>'CRI','Avaí'=>'AVA',
        'CRB'=>'CRB','Operário-PR'=>'OPE','Amazonas'=>'AMA','Paysandu'=>'PAY',
        'Botafogo-SP'=>'BFC','Ferroviária'=>'FER','América-MG'=>'AME',
        'Athletic'=>'ATH','Cuiabá'=>'CUI','Volta Redonda'=>'VRE',
    ];
    return $map[$teamName] ?? null;
}

function faixaClassificacaoFromRowClass(string $classAttr): ?string
{
    if (preg_match('/\bzone-1\b/', $classAttr)) return 'libertadores';
    if (preg_match('/\bzone-2\b/', $classAttr)) return 'pre-libertadores';
    if (preg_match('/\bzone-3\b/', $classAttr)) return 'sul-americana';
    if (preg_match('/\bzone-4\b/', $classAttr)) return 'rebaixados';
    return null;
}

/**
 * Quantas posições o time subiu (positivo) ou desceu (negativo).
 *
 * O número vem do texto da célula ("Subiu1", "Desceu2"), presente apenas
 * para quem mudou de posição. A classe da célula não serve para isso: o
 * Terra marca "movement up" até em quem não se moveu, inclusive no líder.
 */
function parseMovement(string $movementText): int
{
    $t = trim(preg_replace('/\s+/u', ' ', $movementText) ?? $movementText);
    if ($t === '') return 0;

    if (preg_match('/Subiu\s*(\d+)/iu', $t, $m))  return (int)$m[1];
    if (preg_match('/Desceu\s*(\d+)/iu', $t, $m)) return -((int)$m[1]);
    return 0;
}

function parseStandings(string $html): array
{
    libxml_use_internal_errors(true);

    $dom = new DOMDocument();
    if (!$dom->loadHTML('<?xml encoding="utf-8" ?>' . $html)) {
        throw new RuntimeException("Falha ao carregar HTML no DOMDocument");
    }

    $xp = new DOMXPath($dom);

    $rows = $xp->query('//table//tr');
    if (!$rows || $rows->length === 0) {
        throw new SemTabelaException("A página não traz tabela de classificação");
    }

    $dados = [];
    $posicoesVistas = [];

    foreach ($rows as $tr) {
        /** @var DOMElement $tr */
        $teamName = normalizeTeamName(
            (string) $xp->evaluate('string(.//td[contains(@class,"team-name")])', $tr)
        );
        if ($teamName === '') {
            continue; // cabeçalho ou linha sem time
        }

        $pos = (int) trim($xp->evaluate('string(.//td[contains(@class,"position")])', $tr));
        if ($pos <= 0 || isset($posicoesVistas[$pos])) {
            continue;
        }
        $posicoesVistas[$pos] = true;

        $classAttr = $tr->getAttribute('class') ?? '';
        $timeId    = $tr->getAttribute('data-idteam');

        $pts = (string) $xp->evaluate('string(.//td[contains(@class,"points")])', $tr);
        if (trim($pts) === '') {
            $pts = (string) $xp->evaluate('string(.//td[@title="Pontos"])', $tr);
        }

        $movText = (string) $xp->evaluate('string(.//td[contains(@class,"movement")])', $tr);

        $dados[] = [
            'posicao' => $pos,
            'pontos'  => (int) trim($pts),
            'time'    => [
                'time_id'      => is_numeric($timeId) ? (int) $timeId : null,
                'nome_popular' => $teamName,
                'sigla'        => teamSigla($teamName),
            ],
            'jogos'              => (int) trim($xp->evaluate('string(.//td[@title="Jogos"])', $tr)),
            'vitorias'           => (int) trim($xp->evaluate('string(.//td[@title="Vitórias"])', $tr)),
            'empates'            => (int) trim($xp->evaluate('string(.//td[@title="Empates"])', $tr)),
            'derrotas'           => (int) trim($xp->evaluate('string(.//td[@title="Derrotas"])', $tr)),
            'gols_pro'           => (int) trim($xp->evaluate('string(.//td[@title="Gols Pró"])', $tr)),
            'gols_contra'        => (int) trim($xp->evaluate('string(.//td[@title="Gols Contra"])', $tr)),
            'saldo_gols'         => (int) trim($xp->evaluate('string(.//td[@title="Saldo de Gols"])', $tr)),
            'aproveitamento'     => (int) trim($xp->evaluate('string(.//td[@title="Aproveitamento"])', $tr)),
            'variacao_posicao'   => parseMovement($movText),
            'ultimos_jogos'      => [],
            'faixa_classificacao'=> faixaClassificacaoFromRowClass($classAttr),
        ];
    }

    if (count($dados) < MIN_TIMES) {
        throw new SemTabelaException(
            'A página não traz tabela de classificação (' . count($dados) . ' linhas)'
        );
    }

    usort($dados, static fn(array $a, array $b): int => $a['posicao'] <=> $b['posicao']);

    return ['timestamp' => time(), 'dados' => $dados];
}

function saveJsonAtomic(string $path, string $json): void
{
    $dir = dirname($path);
    if (!is_dir($dir)) {
        throw new RuntimeException("Diretório não existe: {$dir}");
    }
    if (!is_writable($dir)) {
        throw new RuntimeException("Sem permissão de escrita no diretório: {$dir}");
    }

    $tmp = $path . '.tmp';
    $bytes = file_put_contents($tmp, $json, LOCK_EX);
    if ($bytes === false) {
        throw new RuntimeException("Falha ao escrever tmp: {$tmp}");
    }

    if (!@rename($tmp, $path)) {
        @unlink($tmp);
        throw new RuntimeException("Falha ao renomear tmp para cache");
    }

    @chmod($path, 0644);
}

function shouldUpdate(string $filePath, int $minIntervalSeconds): bool
{
    if (!is_file($filePath)) return true;

    $age = time() - filemtime($filePath);
    if ($age < 0) return true;

    return $age >= $minIntervalSeconds;
}

/** Caminho do arquivo de espera usado quando a série está sem tabela. */
function flagSemTabela(string $privateDir, string $label): string
{
    return $privateDir . '/sem_tabela_' . $label . '.flag';
}

function emEsperaSemTabela(string $privateDir, string $label, int $cooldown): bool
{
    $flag = flagSemTabela($privateDir, $label);
    if (!is_file($flag)) return false;

    $age = time() - filemtime($flag);
    if ($age < 0) return false;

    return $age < $cooldown;
}

// Garante que o diretório privado existe (necessário para log e lock)
if (!is_dir($PRIVATE_DIR)) {
    @mkdir($PRIVATE_DIR, 0755, true);
}

$lockFp = @fopen($LOCK_PATH, 'c');
if ($lockFp === false) {
    exit(2); // sem lock não dá para rodar com segurança
}

if (!@flock($lockFp, LOCK_EX | LOCK_NB)) {
    @fclose($lockFp); // outra execução em andamento — sai limpo
    exit(0);
}

$hadError = false;

try {
    foreach ($SOURCES as $label => $cfg) {
        $url  = $cfg['url'];
        $file = $cfg['file'];

        if (!shouldUpdate($file, $MIN_INTERVAL_SECONDS)) {
            continue;
        }

        if (emEsperaSemTabela($PRIVATE_DIR, $label, $SEM_TABELA_COOLDOWN)) {
            continue; // já sabemos que esta série está sem tabela agora
        }

        try {
            $html    = fetchUrl($url);
            $payload = parseStandings($html);

            $json = json_encode(
                $payload,
                JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT
            );
            if ($json === false) {
                throw new RuntimeException("Falha ao gerar JSON: " . json_last_error_msg());
            }

            saveJsonAtomic($file, $json);
            @unlink(flagSemTabela($PRIVATE_DIR, $label));
            logLine($LOG_PATH, "OK: Série {$label} atualizada (" . count($payload['dados']) . " times)");

        } catch (SemTabelaException $e) {
            // Não é falha de rede nem do script: a página simplesmente não
            // tem tabela agora. Marcamos a espera e seguimos sem erro.
            @touch(flagSemTabela($PRIVATE_DIR, $label));
            logLine(
                $LOG_PATH,
                "AVISO: Série {$label}: " . $e->getMessage()
                . '. O JSON anterior foi mantido; nova tentativa em '
                . round($SEM_TABELA_COOLDOWN / 3600) . 'h.'
            );

        } catch (Throwable $e) {
            $hadError = true;
            logLine($LOG_PATH, "ERRO: Série {$label}: " . $e->getMessage());
        }
    }

    exit($hadError ? 1 : 0);

} finally {
    @flock($lockFp, LOCK_UN);
    @fclose($lockFp);
}
