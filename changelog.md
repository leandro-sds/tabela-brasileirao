# 📜 Changelog

## [2026.11.24]
- Botão **Atualizar tabela** agora busca a classificação direto da fonte, no momento do clique, em vez de esperar o cache do servidor. Se a fonte não responder, o servidor é usado como plano B, sem mensagem de erro.
- Infraestrutura de dados migrada para **www.leandross.com.br**.
- Correção: o rótulo do botão virava "Atualizar agora" depois da primeira atualização; agora continua "Atualizar tabela".
- A classificação obtida direto da fonte também passa a alimentar o cache local, então reabrir a janela mostra o dado novo.
- Quando a série está entre temporadas ou em fase de playoff, o complemento avisa que ainda não há classificação nova, em vez de dizer que a fonte está indisponível. São situações diferentes e agora têm mensagens diferentes.
- Correção: ao atualizar, a lista voltava sempre ao 1º colocado. Agora ela volta no time que estava selecionado, mesmo que ele tenha mudado de posição.
- Correção: **Copiar tabela** e **Ctrl+C** anunciavam sucesso mesmo quando a área de transferência estava presa por outro programa. Agora o anúncio reflete o que aconteceu de verdade.
- Correção: clicar em Atualizar com uma busca em andamento mostrava um diálogo de erro depois do aviso para aguardar. Agora só avisa.
- Correção: fechar a janela com Esc durante a atualização deixava de gerar erro no log do NVDA.
- A ajuda (F1) agora descreve os botões da janela, inclusive o que o Atualizar tabela faz.

## [2026.7.13]
- Removida a função **Próximos Jogos** e seu atalho **Ctrl+Shift+J**.
- Interface simplificada: botão "Próximos Jogos" removido da janela da tabela.
- Limpeza interna: código, cache e dependências relacionados aos jogos foram removidos.

## [2026.6.17]
- Infraestrutura de dados migrada para o site do desenvolvedor: **www.wpacessivel.com.br**.
- Atualização automática da tabela a cada 30 minutos.
- Sem mudanças visíveis na interface; todas as funcionalidades preservadas.

## [2026.5.02]
- Ajustada a compatibilidade para NVDA 2026.1

## [2026.4.13]
- Reintroduzido suporte à **Série B**.
- Botões **Tabela Série A** e **Tabela Série B** de volta na janela.
- Ao trocar de série, a janela atual permanece aberta em caso de erro.
- Limpeza de código: removido import não utilizado e atributos desnecessários.

## [2026.4.11]
- Infraestrutura de dados migrada para repositório próprio do autor no GitHub.
- Removida dependência de servidor externo para atualização da tabela.
- Adicionada seção de **Próximos Jogos** mantida pelo autor.
- Limpeza geral do código: removidas referências obsoletas e simplificada a arquitetura interna.

## [2026.4.01]
- Removido suporte à **Série B** (mantido apenas Série A).

## [2026.3.17]
- Adicionado botão para consultar os próximos confrontos, com atalho **Control + Shift + J**.

## [2026.3.06]
- Adicionados os atalhos **Ctrl+C** (copia classificação do time selecionado), **Ctrl+A** (copia tabela completa) e **Ctrl+S** (salva tabela em TXT).

## [2026.3.03]
- Adicionado suporte à **Série B**.
- Incluídos botões **Tabela Série A** e **Tabela Série B** na janela.
- Cache separado por série.

## [2026.2.28]
- Encerrada a parceria com api-futebol. Fonte de dados migrada para servidor próprio.

## [2026.2.16]
- Ajustada a compatibilidade com **NVDA 2025.3.3**.

## [2026.2.10]
- Adicionada a função **ajuda** na tecla **F1**.

## [2026.2.08]
- Corrigido o `readme.html` da ajuda.

## [2026.2.06]
- Primeira versão pública.
