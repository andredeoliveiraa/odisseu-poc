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
  64 seções, mas pode ser alterada entre 4 e 512.
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
- Escolha um dos 10 perfis navais na barra superior; depois edite seus parâmetros
  livremente no painel antes de atualizar o modelo.
- A quantidade de linhas longitudinais é mantida separadamente para cada perfil:
  alterar a resolução de um casco não altera os demais.
- O painel é dividido em abas, com controles de barra deslizante e campo
  numérico. Com **Atualizar ao vivo** marcado, o casco é redesenhado enquanto
  os controles são ajustados, sem mover a câmera.
  - **Casco:** dimensões, forma (borda livre, espelho, pé de caverna,
    concavidade), malha e restrições.
  - **Ajuste:** abaulamento do convés, curvatura do espelho para ré, abertura
    das obras mortas e altura do convés (tosamento) na proa e na popa.
  - **Quina:** quina viva (hard chine) ligável, com altura na proa e na popa
    (% do pontal), largura e ângulo do flat da quina.
  - **Redans:** até 3 degraus no fundo, cada um ligável, com posição (% do
    comprimento a partir da proa), altura na quilha e na quina, ângulo com a
    linha de estação e arco. Exigem quina.
  - **Objeto:** deslocar, girar e escalar o modelo inteiro.
- Use **Atualizar modelo 3D** para recalcular o casco e reenquadrar a câmera.
- O menu **Visualizar** tem as cinco vistas padronizadas do conjunto ShipD:
  frontal (`1`), perfil (`2`, proa à direita), planta (`3`), três-quartos pela
  proa a boreste (`4`) e três-quartos pela popa a bombordo (`5`).

## Desempenho

A aba **Desempenho** segue o método de avaliação do artigo *Ship-D: Ship Hull
Dataset for Design Optimization using Machine Learning* (Bagazinski e Ahmed,
2023):

- **Hidrostática** na linha d'água (z = 0): volume, deslocamento, LWL, BWL,
  calado, superfície molhada, área de flutuação, Cb, Cp, Cm, Cw, LCB, LCF e KM.
  É calculada sobre a própria malha, recortando-a na linha d'água e aplicando o
  teorema da divergência, o que é exato para um poliedro.
- **Resistência ao avanço** `Rt = Rw + Rf` de Fn 0,15 a 0,45 (a faixa do
  artigo) e na velocidade de projeto escolhida: ondas pela integral de Michell
  e atrito pela linha ITTC-57, `Cf = 0,075 / (log10 Re − 2)²`. O gráfico mostra
  as três parcelas e a potência efetiva ao passar o mouse; a tabela da curva
  traz os mesmos valores em texto.
- A curva é calculada em segundo plano; a hidrostática atualiza na hora.

A integral de Michell é uma teoria de navio delgado em regime de deslocamento.
Para cascos largos (L/B abaixo de ≈6) ou acima de Fn ≈ 0,5 o painel avisa que o
valor é indicativo: serve para comparar formas, não como previsão absoluta. A
implementação foi validada no casco de Wigley (hidrostática exata e
convergência da integral) em `tests/test_hydrodynamics.py`.
- Importe malhas STL, OBJ, PLY, VTK ou VTP pelo menu **Arquivo > Abrir casco**
  ou arrastando o arquivo para a janela.
- Desloque, rotacione ou redimensione o modelo inteiro no grupo
  **Transformar objeto**.
- Use `Ctrl+Z` e `Ctrl+Y` para desfazer e refazer transformações.
- Exporte o modelo visível em STL, PLY, VTK ou VTP.
- Use o mouse para orbitar, deslocar e aproximar a câmera.
- Pressione `F` para enquadrar o modelo e `Home` para redefinir a vista.

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

Malhas importadas já podem ser transformadas e convertidas. A seleção e edição
direta de seus pontos e faces fará parte da próxima etapa do MVP.

## Testes

```powershell
python -m unittest discover -v
```
