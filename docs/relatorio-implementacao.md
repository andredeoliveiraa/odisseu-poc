# Relatório: adequação do Odisseu à tese ModiYacht

## 1. Objetivo
Aproximar o sistema da tese *Development of a CAD System for Parametric and Attribute-Based Modification of Yacht Hull Models* (Khan, ITU, 2017). A análise inicial mostrou que o S-TLBO e os atributos já existiam. O gerador do casco era outro: seções parabólicas com 6 parâmetros, enquanto a tese usa regiões com Bézier, patches de Coons e 28 parâmetros.

## 2. Diagnóstico inicial

| Item da tese | Situação antes |
|---|---|
| Regiões Entrada, Meio e Popa; curvas de Bézier; patches de Coons | Ausente |
| 28 parâmetros (Tabela 3.2) | Só 6 a 8 parâmetros |
| 14 operadores de forma (Grupos 1 e 2) com abordagem iterativa | Ausente |
| Quina dupla, espessura de quilha, cascos SD, P e D | Ausente |
| Hidrostática (Tabela 3.6) | Ausente |
| Inspeção de fairness (zebra, seções, curvatura) | Ausente |
| S-TLBO conforme a equação 4.15 | Parcial: custo simplificado e sem U₂/U₃ |
| Atributos sobre as 11 variáveis da Tabela 4.1 | Parcial: usava outras variáveis |
| Interface da Figura 5.3 (Grupos 1 e 2) e da Figura 5.8 (atributos) | Parcial |

## 3. O que foi implementado

**Modelo paramétrico**
- `bezier.py`: Bézier cúbica, curvatura, raio mínimo e abordagem iterativa (F, ξ=1000, µ=15). Também resolve o raio mínimo de curvatura e o seu máximo alcançável.
- `hull_model.py`: regiões, estações, curvas características, patches de Coons espelhados e medição dos 28 parâmetros.
- `hull_types.py`: cascos iniciais SD, P e D. O SD reproduz a Tabela 3.4 inteira.
- `mesh.py`: malha com fusão de vértices.

**Operadores de forma** (`shape_operators.py`)
- Grupo 1: alongamento, alargamento, aprofundamento, posição e espessura da quina, inserir/remover quina, espessura da quilha, altura da roda de proa e ângulos de proa, entrada e tosamento.
- Grupo 2: raio mínimo e concavidade das estações.
- Preservam G0/G1 nas estações (desvio medido: 0°). Cada um leva menos de 1 s; a tese cita menos de 4 s.
- Raio inalcançável gera aviso com o limite máximo da curva, como na Figura 5.5.

**Hidrostática** (`hydrostatics.py`)
- Todas as colunas da Tabela 3.6, para três calados, com exportação em CSV.
- Validada contra uma caixa com solução exata.

**Amostragem e atributos** (`sampling.py`, `attributes.py`, `workers.py`)
- S-TLBO conforme o capítulo 4:
  - custo U₁ + αU₂ + βU₃ (α=100, β=1000);
  - seleção gulosa de professores;
  - critério de parada;
  - restrições dos 3 participantes (Tabela 4.1).
- Executa em segundo plano, com progresso e cancelamento.
- 10 atributos sobre as 11 variáveis da Tabela 4.1.

**Interface**
- `parameter_panel.py`: diálogos do Grupo 1 e do Grupo 2; só os campos alterados são aplicados.
- `attribute_panel.py`, `hydrostatic_panel.py`, `curvature_dialog.py`.
- Menu Visualizar com zebra, seções, curvas características, polígonos de controle e gráfico de curvatura.
- Janela principal com botões SD, P e D.

## 4. Verificação
- 152 testes automatizados passando (o conjunto antigo tinha 45).
- Cobertura nova:
  - Bézier e IA;
  - cada operador (valor atingido, parâmetros vizinhos intocados, G1, malha fechada);
  - hidrostática;
  - S-TLBO;
  - atributos.
- Teste de fumaça da janela em modo offscreen: fluxo completo sem erros.
- A suíte leva cerca de 80 segundos.

## 5. Diferenças deliberadas em relação à tese
1. **Atributos:** os coeficientes de Dogan estão truncados na Figura 5.6. Usei um modelo substituto com a mesma estrutura e o mesmo limiar de 0,5.
2. **Similaridade F:** calculada sobre a curvatura e não sobre o raio, para evitar o infinito nos trechos retos.
3. **Penalidade do S-TLBO:** a contagem de restrições violadas ganhou um termo pequeno de desempate pelo grau da violação.
4. **Parada do S-TLBO:** a paciência é maior que as duas iterações da tese, por causa das penalidades discretas.
5. **Colapso:** a busca principal deixava cerca de 18 de 30 projetos em colapso; uma etapa final de reparo zera o colapso (N = 30, sem restrições) com U₁ ≈ 233–242, contra 241,78 na tese. Com atributos muito restritivos o colapso pode permanecer.
6. **Tabela 4.1:** o "110 ≤ β ≤ 80" do participante 3 é impossível, então li como 80 ≤ β ≤ 120.
7. **Eixos:** x é o comprimento, y a boca e z a vertical; a tese usa Z no comprimento.
8. **Espessuras:** as de quina e de quilha são derivadas de uma curva central e variam suavemente entre as estações.

## 6. Segunda rodada: lacunas fechadas

Depois do primeiro relatório ficaram sete pontos em aberto. Situação de cada um:

| Ponto | Resultado |
|---|---|
| Hidrostática sem comparação com a Tabela 3.6 | Comparada. O casco SD foi calibrado (busca em paralelo sobre os ângulos das tangentes) e ficou com erro mediano de 4,3 % (máximo 11 %) contra a tabela. Operadores validados sem entrar no ajuste: quilha K = 0,5 m (3,0 % / 11 %), alongamento Lₘ + 3 m (3,6 % / 11 %), alargamento Bₑ + 1 m (7,4 % / 28 %) |
| Convenção do KB | A tabela da tese traz KB ≈ T/3, coerente só se for contado da linha d'água. O Odisseu mede da quilha (padrão naval); a conversão é `T − KB`, documentada no código e no README |
| Colapso no S-TLBO (18 de 30) | Etapa de reparo ao final da busca. Com N = 30 e sem restrições: colapso 0 e U₁ = 233–242 (tese: 241,78) |
| Coeficientes de Dogan | **Não recuperáveis.** A Figura 5.6 é uma imagem de 1096 × 519 px, com linhas intermediárias omitidas. O modelo substituto continua, mas agora os coeficientes reais podem ser carregados de `app/data/attribute_models.json` (modelo de partida em `docs/attribute_models.template.json`) |
| Interface só vista offscreen | Conferida na janela real do Windows, com fontes e vista 3D: painéis, sobreposições, hidrostática, operadores, atributos (10 projetos amostrados em 13 s), gráfico de curvatura. As listras de zebra saíam em blocos; passaram a ser traçadas por pixel |
| Sequências da Figura 3.16 | As duas rodam e estão nos testes. Descobri e corrigi um erro que desfazia a troca de ordem entre Fb e H (a troca era um no-op); a mesma correção cobre pontal × quina |
| Testes lentos (≈ 260 s) | 152 testes em 79 s. Além de reduzir populações, a construção do casco caiu de 5,5 s para 0,17 s (busca de curvatura máxima em duas etapas e varredura grossa da família de raios, com a mesma resolução ξ = 10 000) |
| Alterações não commitadas | Primeira rodada commitada (`3283381`); esta rodada vem num commit seguinte |

Limites que permanecem:
- A tese não informa a forma do casco entre as estações; a calibração casa a tabela em ordem de grandeza, não valor a valor. As maiores diferenças estão na concavidade (máx. 45 %) e no aprofundamento de Dₑ − 0,46 m (máx. 52 %; o texto da tese fala em "Dm" numa linha "on ER", então o operador pode ser outro).
- Com atributos muito estreitos (por exemplo cute + aesthetic, 0,1 % do espaço) o colapso não pode ser zerado: os níveis cobrem o espaço inteiro e a região viável não alcança todos.
- Na Figura 3.16(a), De = 2,5 m coincide com Fₑ = 2,5 m da Tabela 3.4; as quinas descem junto (1,5 / 1,5 / 0,9 m).

## 7. Riscos e pendências

- **Arquivos reescritos:** seis arquivos que tinham alterações não commitadas foram reescritos por cima (`main_window.py`, `parameter_panel.py`, `attribute_panel.py`, `hull_controller.py`, `attributes.py`, `sampling.py`), e `hull_generator.py`, `profiles.py`, `constraints.py` e `tests/test_hull_geometry.py` foram removidos. As versões *commitadas* anteriores continuam no histórico git; as alterações não commitadas daquele momento só existem no histórico de versões do OneDrive.
- **Atributos:** sem os coeficientes originais de Dogan, os atributos amostrados não coincidem com os da tese. Há como carregá-los (seção 6).
- **Forma entre as estações:** o casco SD reproduz a Tabela 3.4 exatamente e a Tabela 3.6 em ordem de grandeza (seção 6); não há como saber mais sem o modelo original da tese.
- **Resolvido na segunda rodada:** commit, interface na janela real, colapso do S-TLBO, tempo dos testes.
- **Documentação:** o `README.md` tem a tabela de correspondência com a tese e a validação contra a Tabela 3.6.
