-- ERROR:
(psycopg2.errors.SyntaxError) syntax error at or near "SCHEMABINDING"
LINE 2: WITH SCHEMABINDING
             ^

[SQL: CREATE VIEW "Production"."vProductAndDescription"
WITH SCHEMABINDING
AS
-- View (indexed or standard) to display products and product descriptions by language.
SELECT
    p."ProductID"
    ,p."Name"
    ,pm."Name" AS "ProductModel"
    ,pmx."CultureID"
    ,pd."Description"
FROM "Production"."Product" p
    INNER JOIN "Production"."ProductModel" pm
    ON p."ProductModelID" = pm."ProductModelID"
    INNER JOIN "Production"."ProductModelProductDescriptionCulture" pmx
    ON pm."ProductModelID" = pmx."ProductModelID"
    INNER JOIN "Production"."ProductDescription" pd
    ON pmx."ProductDescriptionID" = pd."ProductDescriptionID";]
(Background on this error at: https://sqlalche.me/e/20/f405)

-- SOURCE DEFINITION:

CREATE VIEW [Production].[vProductAndDescription]
WITH SCHEMABINDING
AS
-- View (indexed or standard) to display products and product descriptions by language.
SELECT
    p.[ProductID]
    ,p.[Name]
    ,pm.[Name] AS [ProductModel]
    ,pmx.[CultureID]
    ,pd.[Description]
FROM [Production].[Product] p
    INNER JOIN [Production].[ProductModel] pm
    ON p.[ProductModelID] = pm.[ProductModelID]
    INNER JOIN [Production].[ProductModelProductDescriptionCulture] pmx
    ON pm.[ProductModelID] = pmx.[ProductModelID]
    INNER JOIN [Production].[ProductDescription] pd
    ON pmx.[ProductDescriptionID] = pd.[ProductDescriptionID];
