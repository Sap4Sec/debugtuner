#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size);

int main(int argc, char *argv[])
{
    if (argc < 2)
    {
        return 1;
    }

    int i = 1;
    for (; i < argc; i++)
    {
        FILE *fp = fopen(argv[i], "rb");
        if (fp == NULL)
        {
            return 1;
        }

        fseek(fp, 0L, SEEK_END);
        size_t file_size = ftell(fp);
        fseek(fp, 0L, SEEK_SET);

        uint8_t *file_content = (uint8_t *)malloc(file_size);
        if (file_content == NULL)
        {
            fclose(fp);
            return 1;
        }

        size_t bytes_read = fread(file_content, sizeof(uint8_t), file_size, fp);
        if (bytes_read != file_size)
        {
            free(file_content);
            fclose(fp);
            return 1;
        }

        LLVMFuzzerTestOneInput(file_content, file_size);

        free(file_content);
        fclose(fp);
    }

    return 0;
}