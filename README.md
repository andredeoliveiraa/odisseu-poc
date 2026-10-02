# Odisseu

Odisseu é um protótipo desktop para modelagem paramétrica e visualização 3D de
cascos de embarcações.

## Como executar

```powershell
pip install -r requirements.txt
python main.py
```

## Fluxo atual do MVP

- Ajuste comprimento, seção média, boca, calado, ângulo de proa, concavidade e
  quantidade de linhas longitudinais no painel lateral. A resolução padrão é de
  64 seções, mas pode ser alterada entre 4 e 512; ela é mantida separadamente
  para cada perfil, então alterar a resolução de um casco não altera os demais.
  Cada campo traz sua unidade e seu intervalo.
- **Pontos por seção** define a resolução transversal (padrão 33, ímpar, entre 5
  e 257). As seções são distribuídas de forma adaptativa: há mais seções onde a
  forma do casco muda (transição para proa e popa) e menos na seção média.
- O casco tem fundo, obras mortas e espelho de popa. Por padrão o convés fica
  aberto, para ver as seções por dentro. Marque **Fechar convés** para obter
  uma malha estanque (sem arestas abertas), necessária para cálculos de volume,
  CFD ou impressão 3D.
- O grupo **Forma do casco** controla a **borda livre** (altura do convés acima
  da linha d'água), a largura do **espelho de popa** (fração da boca; 0 gera
  popa em ponta) e o **pé de caverna** (ângulo do fundo em V junto à quilha). A
  concavidade controla quão cheio é o bojo. A proa fica em +X e a linha d'água em Z = 0.
- O **ângulo de proa** afina apenas a entrada de proa e não altera a popa.
- O **raio mínimo** (Grupo 2) valida a curvatura pedida contra um limite
  estimado para a seção mestra; não molda a geometria diretamente, que é
  controlada pelo pé de caverna e pela concavidade.
- Escolha um dos 10 perfis navais na barra superior; ao editar qualquer campo o
  seletor passa a indicar **Personalizado**, para não rotular o casco com o nome
  de um preset que ele já não segue.
- Use **Atualizar modelo 3D**, `Enter` em qualquer campo ou `Ctrl+Enter` para
  recalcular o casco. O painel avisa quando o formulário está à frente da malha.
- Importe malhas STL, OBJ, PLY, VTK, VTP ou arquivos **.3dm do Rhino** pelo
  menu **Arquivo > Abrir casco** ou arrastando o arquivo para a janela. Do
  Rhino só entram superfícies com malha de exibição já salva no arquivo, e
  imagens de referência coladas na cena (comando "Picture") são ignoradas
  automaticamente, por não fazerem parte do casco.
- Desloque, rotacione ou redimensione o modelo inteiro no grupo
  **Transformar objeto**. A câmera é preservada a cada operação.
- Use `Ctrl+Z` e `Ctrl+Y` para desfazer e refazer transformações. O histórico
  guarda as 20 operações mais recentes.
- Exporte o modelo visível em STL, PLY, VTK ou VTP.
- Use o mouse para orbitar, deslocar e aproximar a câmera.
- Pressione `F` para **enquadrar o modelo** mantendo a orientação atual, e
  `Home` para voltar à **vista isométrica**.

## Modelagem por atributos

A aba **Atributos** segue a seção 5.2 e a Figura 5.6 da tese *Parametric Yacht
Models* (ModiYacht):

- Cada um dos 10 atributos (Strong, Speedy, Comfortable, Aesthetic, Usual,
  Aggressive, Compact, Modern, Charismatic, Cute) é avaliado por um polinômio no
  formato GMDH (termos lineares, `cubert`, quadráticos e produtos) sobre os
  parâmetros **padronizados** do casco. O casco expressa o atributo quando o
  valor é maior que 0,5. A avaliação é atualizada enquanto os campos são editados.
- Em **Gerar cascos por atributo**, escolha um ou mais atributos e o número de
  projetos (N). O S-TLBO amostra N cascos distintos que satisfazem todos os
  atributos; o controle deslizante percorre os projetos amostrados.

Os coeficientes de Dogan dependem das curvas de forma do ModiYacht e aparecem
truncados na figura. Por isso `app/models/attributes.py` usa um **modelo
substituto** com a mesma estrutura, calibrado para os parâmetros deste gerador;
ele pode ser trocado por coeficientes ajustados a dados de pesquisa.

Malhas importadas já podem ser transformadas e convertidas. Um arquivo .3dm
também pode ser aberto para edição direta de superfície, pelo menu
**Arquivo > Editar superfície NURBS...**: escolha uma das superfícies com
malha de exibição do arquivo e arraste seus pontos de controle na cena 3D para
remodelá-la em tempo real. **Concluir edição de superfície** mantém o
resultado como modelo atual, e **Salvar superfície como .3dm...** exporta só a
superfície editada para um novo arquivo Rhino.

## Testes

```powershell
python -m unittest discover -v
```
