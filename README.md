# Odisseu

Odisseu é um protótipo desktop para modelagem paramétrica e visualização 3D de
cascos de embarcações.

## Como executar

```powershell
pip install -r requirements.txt
python main.py
```

## Fluxo atual do MVP

- Ajuste comprimento, seção média, boca, calado e concavidade no painel lateral.
- Escolha um dos 10 perfis navais na barra superior; depois edite seus parâmetros
  livremente no painel antes de atualizar o modelo.
- Use **Atualizar modelo 3D** para recalcular o casco.
- Importe malhas STL, OBJ, PLY, VTK ou VTP pelo menu **Arquivo > Abrir casco**
  ou arrastando o arquivo para a janela.
- Desloque, rotacione ou redimensione o modelo inteiro no grupo
  **Transformar objeto**.
- Use `Ctrl+Z` e `Ctrl+Y` para desfazer e refazer transformações.
- Exporte o modelo visível em STL, PLY, VTK ou VTP.
- Use o mouse para orbitar, deslocar e aproximar a câmera.
- Pressione `F` para enquadrar o modelo e `Home` para redefinir a vista.

Malhas importadas já podem ser transformadas e convertidas. A seleção e edição
direta de seus pontos e faces fará parte da próxima etapa do MVP.

## Testes

```powershell
python -m unittest discover -v
```
