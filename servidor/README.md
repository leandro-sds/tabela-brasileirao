# Backend da tabela

Estes arquivos não fazem parte do complemento do NVDA — o build empacota só a
pasta `addon/`. Eles rodam na hospedagem e alimentam os arquivos JSON que o
complemento lê.

## Como funciona

A cada 30 minutos, o cron executa o `update_tabela.php`. Ele lê a página de
classificação do Terra, extrai a tabela da Série A e da Série B e grava dois
arquivos JSON numa pasta pública do site:

- `https://www.leandross.com.br/tabela/cache_tabela_A.json`
- `https://www.leandross.com.br/tabela/cache_tabela_B.json`

O complemento usa esses arquivos ao abrir a janela, porque são leves e
respondem na hora. O botão **Atualizar tabela** não passa por aqui: ele lê a
classificação direto da fonte, no momento do clique, e só cai nestes JSONs se
a fonte não responder.

O `.htaccess` impede que a listagem da pasta `/tabela/` apareça e manda quem
abrir esse endereço para a página inicial do site. Os JSONs continuam
acessíveis um por um, normalmente.

## Onde cada arquivo vai

A pasta `privado/` fica **fora** da pasta pública do site, para que o script e
o log não sejam acessíveis pela web:

    /home2/SEU_USUARIO/privado/update_tabela.php

A pasta `publico/tabela/` é a pasta pública do domínio:

    /home2/SEU_USUARIO/leandross.com.br/tabela/.htaccess

> **Atenção:** `SEU_USUARIO` é um espaço reservado. Este repositório é público,
> e o nome de usuário do cPanel não deve ficar registrado aqui — com ele em
> mãos, só falta a senha para tentar entrar no painel ou no FTP. O valor real
> está nas duas primeiras variáveis do `update_tabela.php` que roda no
> servidor. Ao restaurar a partir deste repositório, ajuste as duas linhas.

Permissões: pastas `755`, arquivos `644`.

Além desses dois, o script cria sozinho, dentro de `privado/`:

- `update_tabela.log` — o que deu certo e o que deu errado
- `update_tabela.lock` — evita duas execuções ao mesmo tempo
- `sem_tabela_A.flag` / `sem_tabela_B.flag` — ver "Fim de temporada", abaixo

## Cron

No cPanel, em Trabalhos Cron. Minuto `0,30`, os outros quatro campos `*`:

    /opt/cpanel/ea-php83/root/usr/bin/php /home2/SEU_USUARIO/privado/update_tabela.php >/dev/null 2>&1

O caminho do PHP muda conforme a versão. Em MultiPHP Manager dá para ver qual
o site usa; `ea-php83` corresponde ao PHP 8.3. Se o caminho estiver errado, o
cron responde `No input file specified` ou `Could not open input file`.

Na primeira execução, vale deixar sem o `>/dev/null 2>&1` e preencher o campo
de e-mail da página de cron: assim qualquer erro chega por e-mail.

## Testar na mão

    /opt/cpanel/ea-php83/root/usr/bin/php /home2/SEU_USUARIO/privado/update_tabela.php
    cat /home2/SEU_USUARIO/privado/update_tabela.log

Esperado:

    [...] OK: Série A atualizada (20 times)
    [...] OK: Série B atualizada (20 times)

## Fim de temporada e fase de playoff

Quando uma série encerra os pontos corridos, o Terra tira a tabela de
classificação daquela página e põe um quadro de playoff no lugar. Não existe
mais tabela para ler, e isso não é defeito do script.

Foi o que aconteceu com a Série B em 17/11/2026: o script passou a falhar em
todas as execuções, gravando 48 mensagens de erro por dia.

O script separa esse caso de uma falha real. Quando a página responde mas não
traz classificação, ele:

1. mantém o JSON anterior intocado, que passa a valer como classificação final
   da temporada;
2. grava uma linha de `AVISO` em vez de `ERRO`, e termina com código de saída 0;
3. cria `sem_tabela_<série>.flag` e só tenta de novo 6 horas depois.

Isso derruba de 48 mensagens por dia para 4. Quando a tabela volta, na
temporada seguinte, a flag é apagada sozinha e tudo segue sem intervenção.

A espera fica na variável `$SEM_TABELA_COOLDOWN`.

## Se quiser a tabela mais fresca ao abrir a janela

O botão **Atualizar tabela** sempre traz o número do momento. O que tem atraso
é a abertura da janela, que usa cache para responder na hora.

São dois intervalos somados:

- no servidor: `$MIN_INTERVAL_SECONDS` no PHP, mais a frequência do cron
- no complemento: `CACHE_TTL_SECONDS` em `addon/globalPlugins/tabelaBrasileirao.py`

Os três estão em 30 minutos. Para reduzir, mude os três juntos — por exemplo,
cron a cada 10 minutos com `$MIN_INTERVAL_SECONDS = 600` e
`CACHE_TTL_SECONDS = 600`. O custo é consultar a fonte 6 vezes por hora em vez
de 2, e o servidor ser consultado mais vezes por cada usuário.

## Por que existe um servidor no meio

Seria possível o complemento ler sempre direto da fonte, sem este backend. A
razão para não fazer isso é manutenção: se a página mudar de estrutura, aqui
basta corrigir o PHP uma vez e todos os usuários voltam a funcionar na hora.
Sem o servidor no meio, cada um precisaria baixar uma versão nova do
complemento.

A estrutura da página muda de verdade — a troca da tabela pelo quadro de
playoff, em novembro de 2026, é um exemplo.
