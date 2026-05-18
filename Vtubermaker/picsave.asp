<%@CODEPAGE=65001 %>
<%
    Response.CharSet = "utf-8"
    
    ' 1. 데이터 받기
    Dim rawData
    rawData = Request.Form("imgData")

    If rawData = "" Then
        Response.Write "데이터가 전송되지 않았습니다."
        Response.End
    End If

    ' 2. Base64 데이터 순수화 (접두어 제거 및 공백 처리)
    Dim base64Data
    If InStr(rawData, ",") > 0 Then
        base64Data = Mid(rawData, InStr(rawData, ",") + 1)
    Else
        base64Data = rawData
    End If
    
    ' 간혹 공백이 +로 변환되지 않아 생기는 오류 방지
    base64Data = Replace(base64Data, " ", "+")

    ' 3. 디코딩 (MSXML 사용)
    Dim xmlDoc, node
    Set xmlDoc = Server.CreateObject("MSXML2.DOMDocument.3.0")
    Set node = xmlDoc.CreateElement("base64")
    node.dataType = "bin.base64"
    node.text = base64Data
    
    ' 바이너리 데이터 추출
    Dim binaryData
    binaryData = node.nodeTypedValue

    ' 4. 경로 및 파일명 설정
    Dim folderPath, fileName, fullPath
    folderPath = Server.MapPath("./photos")
    
    ' 폴더 생성 (FSO)
    Dim fso
    Set fso = Server.CreateObject("Scripting.FileSystemObject")
    If Not fso.FolderExists(folderPath) Then
        fso.CreateFolder(folderPath)
    End If

    fileName = "v_photo_image.png" '이미지 위치 중요!!!!!
    fullPath = folderPath & "\" & fileName

    Dim objStream
    Set objStream = Server.CreateObject("ADODB.Stream")
    
    objStream.Type = 1 
    objStream.Open
    
    If Not IsNull(binaryData) Then
        objStream.Write binaryData
        objStream.SaveToFile fullPath, 2 ' 2 = adSaveCreateOverWrite
        Response.Write "성공|파일명: " & fileName
    Else
        Response.Write "실패|이미지 변환 중 오류 발생"
    End If

    objStream.Close
    Set objStream = Nothing
    Set fso = Nothing
    Set node = Nothing
    Set xmlDoc = Nothing
%>