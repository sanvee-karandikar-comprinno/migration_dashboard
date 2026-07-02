-- ERROR:
(psycopg2.errors.FeatureNotSupported) cross-database references are not implemented: s.Demographics.value
LINE 5:     ,s."Demographics"."value"('declare default element names...
             ^

[SQL: CREATE OR REPLACE VIEW "Sales"."vStoreWithDemographics" AS
SELECT
    s."BusinessEntityID"
    ,s."Name"
    ,s."Demographics"."value"('declare default element namespace "http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/StoreSurvey";
        (/StoreSurvey/AnnualSales)[1]', 'money') AS "AnnualSales"
    ,s."Demographics"."value"('declare default element namespace "http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/StoreSurvey";
        (/StoreSurvey/AnnualRevenue)[1]', 'money') AS "AnnualRevenue"
    ,s."Demographics"."value"('declare default element namespace "http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/StoreSurvey";
        (/StoreSurvey/BankName)[1]', 'nvarchar(50)') AS "BankName"
    ,s."Demographics"."value"('declare default element namespace "http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/StoreSurvey";
        (/StoreSurvey/BusinessType)[1]', 'nvarchar(5)') AS "BusinessType"
    ,s."Demographics"."value"('declare default element namespace "http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/StoreSurvey";
        (/StoreSurvey/YearOpened)[1]', 'integer') AS "YearOpened"
    ,s."Demographics"."value"('declare default element namespace "http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/StoreSurvey";
        (/StoreSurvey/Specialty)[1]', 'nvarchar(50)') AS "Specialty"
    ,s."Demographics"."value"('declare default element namespace "http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/StoreSurvey";
        (/StoreSurvey/SquareFeet)[1]', 'integer') AS "SquareFeet"
    ,s."Demographics"."value"('declare default element namespace "http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/StoreSurvey";
        (/StoreSurvey/Brands)[1]', 'nvarchar(30)') AS "Brands"
    ,s."Demographics"."value"('declare default element namespace "http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/StoreSurvey";
        (/StoreSurvey/Internet)[1]', 'nvarchar(30)') AS "Internet"
    ,s."Demographics"."value"('declare default element namespace "http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/StoreSurvey";
        (/StoreSurvey/NumberEmployees)[1]', 'integer') AS "NumberEmployees"
FROM "Sales"."Store" s;]
(Background on this error at: https://sqlalche.me/e/20/tw8g)

-- SOURCE DEFINITION:

CREATE VIEW [Sales].[vStoreWithDemographics] AS
SELECT
    s.[BusinessEntityID]
    ,s.[Name]
    ,s.[Demographics].value('declare default element namespace "http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/StoreSurvey";
        (/StoreSurvey/AnnualSales)[1]', 'money') AS [AnnualSales]
    ,s.[Demographics].value('declare default element namespace "http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/StoreSurvey";
        (/StoreSurvey/AnnualRevenue)[1]', 'money') AS [AnnualRevenue]
    ,s.[Demographics].value('declare default element namespace "http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/StoreSurvey";
        (/StoreSurvey/BankName)[1]', 'nvarchar(50)') AS [BankName]
    ,s.[Demographics].value('declare default element namespace "http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/StoreSurvey";
        (/StoreSurvey/BusinessType)[1]', 'nvarchar(5)') AS [BusinessType]
    ,s.[Demographics].value('declare default element namespace "http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/StoreSurvey";
        (/StoreSurvey/YearOpened)[1]', 'integer') AS [YearOpened]
    ,s.[Demographics].value('declare default element namespace "http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/StoreSurvey";
        (/StoreSurvey/Specialty)[1]', 'nvarchar(50)') AS [Specialty]
    ,s.[Demographics].value('declare default element namespace "http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/StoreSurvey";
        (/StoreSurvey/SquareFeet)[1]', 'integer') AS [SquareFeet]
    ,s.[Demographics].value('declare default element namespace "http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/StoreSurvey";
        (/StoreSurvey/Brands)[1]', 'nvarchar(30)') AS [Brands]
    ,s.[Demographics].value('declare default element namespace "http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/StoreSurvey";
        (/StoreSurvey/Internet)[1]', 'nvarchar(30)') AS [Internet]
    ,s.[Demographics].value('declare default element namespace "http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/StoreSurvey";
        (/StoreSurvey/NumberEmployees)[1]', 'integer') AS [NumberEmployees]
FROM [Sales].[Store] s;
