-- ERROR:
Routine conversion not implemented for mssql -> mysql

-- SOURCE DEFINITION:

CREATE FUNCTION [dbo].[ufnGetAccountingStartDate]()
RETURNS [datetime]
AS
BEGIN
    RETURN CONVERT(datetime, '20030701', 112);
END;
