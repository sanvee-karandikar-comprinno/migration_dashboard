-- ERROR:
(psycopg2.errors.UndefinedTable) relation "Person.contacttype" does not exist
LINE 18:  INNER JOIN "Person".ContactType ct
                     ^

[SQL: CREATE OR REPLACE VIEW "Purchasing"."vVendorWithContacts" AS
SELECT
    v."BusinessEntityID"
    ,v."Name"
    ,ct."Name" AS "ContactType"
    ,p."Title"
    ,p."FirstName"
    ,p."MiddleName"
    ,p."LastName"
    ,p."Suffix"
    ,pp."PhoneNumber"
	,pnt."Name" AS "PhoneNumberType"
    ,ea."EmailAddress"
    ,p."EmailPromotion"
FROM "Purchasing"."Vendor" v
    INNER JOIN "Person"."BusinessEntityContact" bec
    ON bec."BusinessEntityID" = v."BusinessEntityID"
	INNER JOIN "Person".ContactType ct
	ON ct."ContactTypeID" = bec."ContactTypeID"
	INNER JOIN "Person"."Person" p
	ON p."BusinessEntityID" = bec."PersonID"
	LEFT OUTER JOIN "Person"."EmailAddress" ea
	ON ea."BusinessEntityID" = p."BusinessEntityID"
	LEFT OUTER JOIN "Person"."PersonPhone" pp
	ON pp."BusinessEntityID" = p."BusinessEntityID"
	LEFT OUTER JOIN "Person"."PhoneNumberType" pnt
	ON pnt."PhoneNumberTypeID" = pp."PhoneNumberTypeID";]
(Background on this error at: https://sqlalche.me/e/20/f405)

-- SOURCE DEFINITION:

CREATE VIEW [Purchasing].[vVendorWithContacts] AS
SELECT
    v.[BusinessEntityID]
    ,v.[Name]
    ,ct.[Name] AS [ContactType]
    ,p.[Title]
    ,p.[FirstName]
    ,p.[MiddleName]
    ,p.[LastName]
    ,p.[Suffix]
    ,pp.[PhoneNumber]
	,pnt.[Name] AS [PhoneNumberType]
    ,ea.[EmailAddress]
    ,p.[EmailPromotion]
FROM [Purchasing].[Vendor] v
    INNER JOIN [Person].[BusinessEntityContact] bec
    ON bec.[BusinessEntityID] = v.[BusinessEntityID]
	INNER JOIN [Person].ContactType ct
	ON ct.[ContactTypeID] = bec.[ContactTypeID]
	INNER JOIN [Person].[Person] p
	ON p.[BusinessEntityID] = bec.[PersonID]
	LEFT OUTER JOIN [Person].[EmailAddress] ea
	ON ea.[BusinessEntityID] = p.[BusinessEntityID]
	LEFT OUTER JOIN [Person].[PersonPhone] pp
	ON pp.[BusinessEntityID] = p.[BusinessEntityID]
	LEFT OUTER JOIN [Person].[PhoneNumberType] pnt
	ON pnt.[PhoneNumberTypeID] = pp.[PhoneNumberTypeID];
