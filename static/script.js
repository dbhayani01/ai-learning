window.uploadFile = async function () {

    const fileInput = document.getElementById("pdfFile");

    if (!fileInput.files.length) {
        alert("Please select a PDF file.");
        return;
    }

    const formData = new FormData();

    formData.append("file", fileInput.files[0]);

    try {

        const response = await fetch("/upload", {
            method: "POST",
            body: formData
        });

        const result = await response.json();

        document.getElementById("uploadResult").innerText =
            JSON.stringify(result, null, 2);

    } catch (error) {
        console.error(error);
        alert("Upload failed");
    }
};

window.askQuestion = async function () {

    const question =
        document.getElementById("question").value;

    if (!question.trim()) {
        alert("Please enter a question");
        return;
    }

    try {

        const response = await fetch("/ask", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                question: question
            })
        });

        const result = await response.json();

        let html = "";

        html += `
            <h3>Answer</h3>
            <p>${result.answer}</p>
        `;

        html += `
            <h3>Retrieved Chunks</h3>
        `;

        result.chunks.forEach((chunk, index) => {

            html += `
                <div style="
                    border:1px solid #ccc;
                    padding:10px;
                    margin-bottom:10px;
                    border-radius:6px;
                ">
                    <h4>Chunk ${index + 1}</h4>

                    <b>Source:</b>
                    ${chunk.source}
                    <br><br>

                    <pre>${chunk.content}</pre>
                </div>
            `;
        });

        document.getElementById("answer").innerHTML =
            html;

    } catch (error) {

        console.error(error);

        document.getElementById("answer").innerHTML =
            "<p style='color:red;'>Question failed.</p>";
    }
};
