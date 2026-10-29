"""Seed categories (PT-BR) for categorization.

`baseline_rate` = expected sales pace of a TYPICAL SKU of the category in a
physical mercado, in units per customer per day. The public dataset (a
marketplace) only informs the SEASONAL shape (month/weekday/size index via
LightGBM); the absolute level comes from these calibrated baselines — a
marketplace basket is not a supermarket basket.

The mapping of dataset families (EN or PT) to these categories lives with
each dataset adapter in app/services/datasets.py.
"""

SEED_CATEGORIES: list[dict] = [
    {
        "name": "Hortifrúti",
        "baseline_rate": 0.3,
        "description": (
            "Frutas, verduras, legumes e temperos frescos: banana, tomate, alface, "
            "cebola, batata, maçã, laranja, cenoura, alho, limão, mamão, abacate..."
        ),
        "keywords": "banana,tomate,alface,cebola,batata,maçã,maca,laranja,cenoura,alho,limão,limao,mamão,mamao,abacate,manga,melancia,melão,melao,uva,cebola,brócolis,brocolis,abobora,abóbora,pepino,pimenta,repolho,espinafre,rúcula,rucula,couve,cebolinha,coentro,salsinha,manjericão,manjericao,fruta,verdura,legume,produce",
    },
    {
        "name": "Padaria",
        "baseline_rate": 0.6,
        "description": (
            "Pães, bolos, biscoitos, torradas, salgados e itens de padaria em geral: "
            "pão francês, pão de forma, bolo, biscoito, bolacha, torrada, sonho, croissant, broa..."
        ),
        "keywords": "pão,pao,padaria,pão de forma,pao de forma,bolo,biscoito,bolacha,torrada,salgado,sonho,croissant,broa,baguete,croissant,rosca,baguete,waffle,granola,cereal matinal,bolo de cenoura,bolo de chocolate,biscuit,bakery,bread",
    },
    {
        "name": "Bebidas",
        "baseline_rate": 0.25,
        "description": (
            "Refrigerantes, sucos, águas, cervejas, refrigerantes, energéticos, chás e bebidas em geral: "
            "coca-cola, guaraná, suco de laranja, água mineral, cerveja lata, energético, chá gelado..."
        ),
        "keywords": "refrigerante,coca,guaraná,guarana,suco,água,agua,cerveja,energético,energetico,chá,cha,chá gelado,cha gelado,isotônico,isotonico,soda,limonada,vinho,drink,bebida,beverage,jus,water,soda,beer,energetic,suco natural,néctar,nectar",
    },
    {
        "name": "Laticínios e Ovos",
        "baseline_rate": 0.2,
        "description": (
            "Leite, queijos, iogurtes, manteiga, requeijão, ovos e derivados do leite: "
            "leite integral, queijo muçarela, iogurte natural, ovo branco, manteiga com sal, requeijão cremoso..."
        ),
        "keywords": "leite,queijo,iogurte,iovogurt,manteiga,requeijão,requeijao,ovo,ovos,mucarela,muçarela,parmesão,parmesao,ricota,coalho,creme de leite,condensado,danone,ninho,nesfit,milk,cheese,yogurt,egg,dairy,lacteo,lácteo",
    },
    {
        "name": "Carnes e Aves",
        "baseline_rate": 0.15,
        "description": (
            "Carnes bovinas, suínas, aves e embutidos: picanha, contra-filé, frango inteiro, "
            "coxa de frango, linguiça, salame, presunto, costela, carne moída..."
        ),
        "keywords": "carne,picanha,contra-filé,file,filezinho,frango,galinha,coxa,asa,linguiça,linguica,salame,presunto,costela,carne moída,carne moida,bovina,suíno,suino,porco,bacon,paio,mortadela,salsicha,acougue,açougue,meat,chicken,pork,beef",
    },
    {
        "name": "Peixes e Frutos do Mar",
        "baseline_rate": 0.04,
        "description": (
            "Pescados, camarões, frutos do mar frescos e congelados: tilápia, salmão, sardinha, "
            "camarão, polvo, lula, caranguejo..."
        ),
        "keywords": "peixe,tilápia,tilapia,salmão,salmao,sardinha,camarão,camarao,polvo,lula,caranguejo,ostra,mexilhão,mexilhao,atum,bacalhau,pescada,merluza,frutos do mar,seafood,fish",
    },
    {
        "name": "Mercearia",
        "baseline_rate": 0.15,
        "description": (
            "Produtos de despensa e itens gerais de mercearia: arroz, feijão, açúcar, café, "
            "macarrão, farinha, óleo, sal, molhos, conservas, enlatados, temperos..."
        ),
        "keywords": "arroz,feijão,feijao,açucar,açúcar,acucar,café,cafe,macarrão,macarrao,macarrao,farinha,óleo,oleo,sal,molho,conserva,enlatado,tempero,grão,grao,lentilha,grão de bico,grao de bico,atuum,atum,sardinha em lata,milho,ervilha,leite em pó,leite em po,chocolate,barra de chocolate,chocolate em pó,cacau,grocery,despensa",
    },
    {
        "name": "Congelados e Frios",
        "baseline_rate": 0.08,
        "description": (
            "Alimentos congelados, prontos e itens de deli: pizza congelada, lasanha congelada, "
            "hambúrguer congelado, sorvete, gelo, presunto fatiado, queijo fatiado, salame fatiado..."
        ),
        "keywords": "congelado,pizza congelada,lasanha congelada,hambúrguer,hamburguer,sorvete,gelo,presunto fatiado,queijo fatiado,prato pronto,pastel congelado,nugget,batata palha,chipa,frozen,ice cream,sorvete de palito,deli",
    },
    {
        "name": "Limpeza",
        "baseline_rate": 0.05,
        "description": (
            "Produtos de limpeza doméstica: detergente, sabão em pó, amaciante, desinfetante, "
            "água sanitária, esponja, papel higiênico, papel toalha, multiuso..."
        ),
        "keywords": "detergente,sabão,sabao,amaciante,desinfetante,água sanitária,agua sanitaria,esponja,papel higiênico,papel higienico,papel toalha,multiuso,lava louças,limpador,alvejante,sabonete líquido,limpeza,cleaning,bleach,detergent,napkin",
    },
    {
        "name": "Higiene e Beleza",
        "baseline_rate": 0.06,
        "description": (
            "Cuidados pessoais e beleza: shampoo, condicionador, sabonete, creme dental, "
            "desodorante, papel higiênico, absorvente, fralda, creme hidratante, perfume..."
        ),
        "keywords": "shampoo,condicionador,condicionador,sabonete,creme dental,pasta de dente,desodorante,absorvente,fralda,creme hidratante,perfume,gel de cabelo,escova de dente,fio dental,cotonete,beauty,higiene,personal care,soap,toothpaste,deodorant,shampu",
    },
    {
        "name": "Pet e Bebê",
        "baseline_rate": 0.03,
        "description": (
            "Produtos para animais de estimação e para bebês: ração, areia de gato, petisco, "
            "fralda infantil, lenço umedecido, mamadeira, chupeta, papinha de bebê..."
        ),
        "keywords": "ração,rasao,areia de gato,petisco,cachorro,gato,fralda infantil,fralda geriátrica,lenço umedecido,lenco umedecido,mamadeira,chupeta,papinha,nan,aptamil,pet,baby,bebê,bebe,pampers,whiskas,dog Chow,pedigree",
    },
    {
        "name": "Lar e Cozinha",
        "baseline_rate": 0.02,
        "description": (
            "Utilidades domésticas, cozinha e pequenos eletrodomésticos: panela, copo, prato, "
            "talher, guardanapo, pilha, lâmpada, vassoura, liquidificador, ventilador, cachepô..."
        ),
        "keywords": "panela,copo,prato,talher,guardanapo,pilha,lâmpada,lampada,vassoura,liquidificador,ventilador,cachepo,cachepô,tupperware,garrafa térmica,garrafa termica,jogo de cama,toalha de banho,alicate,prego,parafuso,ferramenta,screwdriver,hammer,ferramenta manual,home,kitchen,household",
    },
    {
        "name": "Festa e Papelaria",
        "baseline_rate": 0.02,
        "description": (
            "Artigos de festa, papelaria, livros e revistas: bala, doce, salgadinho para festa, "
            "caderno, caneta, lápis, papel sulfite, envelope, livro, revista, presente..."
        ),
        "keywords": "bala,doce,salgadinho de festa,pipoca,caderno,caneta,lápis,lapis,papel sulfite,envelope,livro,revista,presente,embalagem de presente,vela de aniversário,vela de aniversario,festa,papelaria,school,office,book,magazine,candy,stationery",
    },
    {
        "name": "Diversos",
        "baseline_rate": 0.015,
        "description": (
            "Itens variados que não se encaixam nas demais categorias: roupas, calçados, "
            "acessórios, eletrônicos em geral, decoração, ferramentas específicas, automotivo..."
        ),
        "keywords": "roupa,calça,calca,calçado,calcado,sapato,camiseta,blusa,vestido,meia,eletrônico,eletronico,fone,cabecote,carregador,pilha recarregável,decoração,decoracao,automotivo,óleo de motor,oleo de motor, outros,misc,other,clothing,electronics",
    },
]

DEFAULT_CATEGORY_NAME = "Mercearia"

def size_bucket_from_customers(customers_per_day: int) -> int:
    """Bucket the user's market by customers/day — mirrors the dataset buckets."""
    if customers_per_day < 150:
        return 0
    if customers_per_day < 400:
        return 1
    if customers_per_day < 1200:
        return 2
    return 3

def baseline_by_name(name: str) -> float:
    for spec in SEED_CATEGORIES:
        if spec["name"] == name:
            return spec["baseline_rate"]
    return DEFAULT_BASELINE_RATE


DEFAULT_BASELINE_RATE = 0.08
