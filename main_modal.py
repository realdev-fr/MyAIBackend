import modal

app = modal.App("example-get-started")


@app.function()
def square(x):
    print("This code is running on a remote worker!")
    return x**2

##Run with "modal run main_modal.py"
@app.local_entrypoint()
def main():
    print("the square is", square.remote(42))