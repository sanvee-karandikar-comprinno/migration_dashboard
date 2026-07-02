-- ERROR:
(psycopg2.errors.SyntaxError) syntax error at or near "SCHEMABINDING"
LINE 2: WITH SCHEMABINDING
             ^

[SQL: CREATE VIEW "Person"."vStateProvinceCountryRegion"
WITH SCHEMABINDING
AS
SELECT
    sp."StateProvinceID"
    ,sp."StateProvinceCode"
    ,sp."IsOnlyStateProvinceFlag"
    ,sp."Name" AS "StateProvinceName"
    ,sp."TerritoryID"
    ,cr."CountryRegionCode"
    ,cr."Name" AS "CountryRegionName"
FROM "Person"."StateProvince" sp
    INNER JOIN "Person"."CountryRegion" cr
    ON sp."CountryRegionCode" = cr."CountryRegionCode";]
(Background on this error at: https://sqlalche.me/e/20/f405)

-- SOURCE DEFINITION:

CREATE VIEW [Person].[vStateProvinceCountryRegion]
WITH SCHEMABINDING
AS
SELECT
    sp.[StateProvinceID]
    ,sp.[StateProvinceCode]
    ,sp.[IsOnlyStateProvinceFlag]
    ,sp.[Name] AS [StateProvinceName]
    ,sp.[TerritoryID]
    ,cr.[CountryRegionCode]
    ,cr.[Name] AS [CountryRegionName]
FROM [Person].[StateProvince] sp
    INNER JOIN [Person].[CountryRegion] cr
    ON sp.[CountryRegionCode] = cr.[CountryRegionCode];
